// Deep-link into Splunk Search for a given SPL string, optionally scoped to a time window.
export function splunkSearchLink(web: string, spl: string, earliest?: string, latest?: string) {
  const q = encodeURIComponent(spl);
  const t = earliest && latest ? `&earliest=${encodeURIComponent(earliest)}&latest=${encodeURIComponent(latest)}` : "";
  return `${web}/en-US/app/search/search?q=${q}${t}`;
}
