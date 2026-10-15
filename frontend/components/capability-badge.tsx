import { capabilities, capabilityLabels, type CapabilityKey } from "../lib/capabilities";

/** One-line availability marker shown in the page header. */
export default function CapabilityBadge({ section }: { section: CapabilityKey }) {
  const capability = capabilities[section];
  return <span className="badge" data-variant="outline" title={capability.note} data-capability={capability.status}>
    {capabilityLabels[capability.status]}
    <span className="sr-only">：{capability.note}</span>
  </span>;
}
