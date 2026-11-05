// Will Cook's websites, as the family registry lists them. family.json is an
// unchanged copy of sites.json from https://github.com/wcook04/wcook04.github.io
// (copied here from lean-exposition/site/src/app/family.json), whose
// docs/family.md is the contract for the header lockup and the footer's sister
// sites. Rendering from this copy means the page requests nothing from another host.

import registry from "./family.json";

export interface FamilySite {
  id: string;
  short: string;
  url: string;
}

export const FAMILY = registry as unknown as {
  owner: { name: string; home: string };
  sites: FamilySite[];
};
