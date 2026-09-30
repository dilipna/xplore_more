import type { MetadataRoute } from "next";
import { siteOrigin } from "@/lib/site";

export const dynamic = "force-dynamic";

export default async function robots(): Promise<MetadataRoute.Robots> {
  return { rules: { userAgent: "*", allow: "/" }, sitemap: `${await siteOrigin()}/sitemap.xml` };
}
