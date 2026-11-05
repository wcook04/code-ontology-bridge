// The one place the site reads data. It follows docs/frontend-handoff.md:
// fetch data/index.json, follow its relative manifest, then resolve every
// logical API route through manifest.api_routes relative to that manifest.
// The manifest is pinned for the session, every response must carry the
// manifest's revision, and nothing is substituted when a request fails.

import type { Entry, Envelope, Manifest } from "./types";

export class DataError extends Error {
  constructor(
    message: string,
    readonly kind: "network" | "missing_route" | "revision" | "schema",
  ) {
    super(message);
  }
}

const SUPPORTED_DEPLOYMENT = "cob_deployment_v1";
const SUPPORTED_PUBLICATION = "cob_publication_v1";

export interface Publication {
  entry: Entry;
  manifest: Manifest;
  manifestURL: URL;
}

async function readJSON<T>(url: URL): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url);
  } catch {
    throw new DataError("The published data could not be reached.", "network");
  }
  if (!response.ok) throw new DataError(`The published data returned HTTP ${response.status}.`, "network");
  try {
    return (await response.json()) as T;
  } catch {
    throw new DataError("A published file was not valid JSON.", "schema");
  }
}

let publication: Promise<Publication> | null = null;
const routes = new Map<string, Promise<unknown>>();

export function entryURL(): URL {
  return new URL("data/index.json", document.baseURI);
}

export function loadPublication(): Promise<Publication> {
  if (!publication) {
    publication = (async () => {
      const url = entryURL();
      const entry = await readJSON<Entry>(url);
      if (entry.schema_version !== SUPPORTED_DEPLOYMENT) {
        throw new DataError(`Unsupported deployment format: ${entry.schema_version}`, "schema");
      }
      const manifestURL = new URL(entry.manifest, url);
      const manifest = await readJSON<Manifest>(manifestURL);
      if (manifest.schema_version !== SUPPORTED_PUBLICATION) {
        throw new DataError(`Unsupported publication format: ${manifest.schema_version}`, "schema");
      }
      if (manifest.publication_sha256 !== entry.publication_sha256) {
        throw new DataError("The deployment pointer and its manifest disagree.", "revision");
      }
      return { entry, manifest, manifestURL };
    })();
    publication.catch(() => {
      publication = null;
    });
  }
  return publication;
}

/** The data of one published API route, checked against the pinned manifest's revision. */
export function readRoute<T>(route: string): Promise<T> {
  let pending = routes.get(route) as Promise<T> | undefined;
  if (!pending) {
    pending = (async () => {
      const { manifest, manifestURL } = await loadPublication();
      const asset = manifest.api_routes[route];
      if (!asset) throw new DataError(`This publication does not include ${route}.`, "missing_route");
      const envelope = await readJSON<Envelope<T>>(new URL(asset, manifestURL));
      if (envelope.revision !== manifest.revision) {
        throw new DataError("A response belongs to a different data revision than this page.", "revision");
      }
      return envelope.data;
    })();
    routes.set(route, pending);
    pending.catch(() => routes.delete(route));
  }
  return pending;
}
