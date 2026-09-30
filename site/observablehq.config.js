// Observable Framework config. Data comes from Python loaders in src/data/ reading ../data/parquet.
export default {
  title: "AU Economy, Insurance & AI-Jobs",
  root: "src",
  pages: [
    {name: "Macro", path: "/macro"},
    {name: "Insurance", path: "/insurance"},
    {name: "AI & jobs", path: "/ai-jobs"},
    {name: "About & methods", path: "/about"}
  ],
  theme: ["air", "near-midnight"],
  style: "style.css",
  footer: "Public data only. Descriptive, not causal. Sources and licences on the About page.",
  toc: false,
  search: false
};
