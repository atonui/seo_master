import type { Evidence } from "../api/types";

export function MetricEvidence({ items }: { items: Evidence[] }) {
  return <ul className="evidence-list">{items.map((item) => <li key={item.id}>
    <strong>{item.metric}: {String(item.value)}</strong>
    {item.label && <span>{item.label}</span>}
    <small>{item.source} · {item.period}</small>
  </li>)}</ul>;
}
