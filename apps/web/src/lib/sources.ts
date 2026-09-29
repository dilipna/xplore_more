/**
 * Display names for source ids, copied from the `sources` table (seeded from config/sources.yaml
 * and config/problem_sources.yaml). The feed API returns ids only; unknown ids fall back to a
 * title-cased slug, so a new source still renders sensibly.
 */
const NAMES: Record<string, string> = {
  "anthropic-news": "Anthropic News",
  "ars-technica": "Ars Technica",
  "arxiv-cs-cl": "arXiv cs.CL",
  "arxiv-cs-ir": "arXiv cs.IR",
  "arxiv-cs-lg": "arXiv cs.LG",
  "aws-ml-blog": "AWS Machine Learning Blog",
  "aws-news": "AWS News Blog",
  "chip-huyen": "Chip Huyen",
  "cloudflare-blog": "Cloudflare Blog",
  "dropbox-tech": "Dropbox Tech",
  "eugene-yan": "Eugene Yan",
  "gh-kubernetes": "Kubernetes releases",
  "gh-llama-cpp": "llama.cpp releases",
  "gh-ollama": "Ollama releases",
  "gh-pytorch": "PyTorch releases",
  "gh-transformers": "Transformers releases",
  "gh-vllm": "vLLM releases",
  "github-blog": "GitHub Blog",
  "google-cloud-blog": "Google Cloud Blog",
  "google-deepmind": "Google DeepMind",
  "google-research": "Google Research",
  "hacker-news": "Hacker News",
  "huggingface-blog": "Hugging Face",
  "import-ai": "Import AI",
  infoq: "InfoQ",
  interconnects: "Interconnects",
  "kubernetes-blog": "Kubernetes Blog",
  "lilian-weng": "Lil'Log",
  lobsters: "Lobsters",
  "meta-engineering": "Engineering at Meta",
  "microsoft-research": "Microsoft Research",
  "mit-tech-review": "MIT Technology Review",
  "netflix-techblog": "Netflix TechBlog",
  "nvidia-developer": "NVIDIA Technical Blog",
  "openai-news": "OpenAI News",
  "sebastian-raschka": "Ahead of AI",
  "simon-willison": "Simon Willison",
  "slack-engineering": "Slack Engineering",
  "stripe-blog": "Stripe Blog",
  "techcrunch-ai": "TechCrunch AI",
  "the-register": "The Register",
  "the-verge": "The Verge",
  "venturebeat-ai": "VentureBeat AI",
  "wired-ai": "WIRED AI",
};

export function sourceName(id: string): string {
  return NAMES[id] ?? id.replace(/[-_]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Two-letter avatar initials: "Hacker News" -> "HN", "InfoQ" -> "IN". */
export function initials(name: string): string {
  const words = name.replace(/[^A-Za-z0-9 ]/g, " ").split(/\s+/).filter(Boolean);
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  return (words[0] ?? "?").slice(0, 2).toUpperCase();
}

const HUES = ["#39ff7f", "#4fd1ff", "#ff8a3d", "#c38bff", "#ffd84a", "#ff5c8a", "#5cffd6", "#a8b5ff"];

/** A stable accent colour per source, so the same outlet always gets the same avatar. */
export function sourceColor(id: string): string {
  if (id === "hacker-news") return "#ff8a3d";
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return HUES[h % HUES.length];
}

export function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}
