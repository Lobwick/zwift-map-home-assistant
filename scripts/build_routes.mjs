// Regenerates custom_components/zwift_map/data/routes.json from the
// zwift-data package (MIT, (c) Andi Pätzold, https://github.com/andipaetzold/zwift-data).
//
// Usage:
//   npm pack zwift-data && tar xzf zwift-data-*.tgz
//   node scripts/build_routes.mjs ./package
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const pkgDir = resolve(process.argv[2] ?? "./package");
const zd = await import(pathToFileURL(`${pkgDir}/lib/index.js`).href);
const { version } = (await import(pathToFileURL(`${pkgDir}/package.json`).href, {
  with: { type: "json" },
})).default;

const worlds = Object.fromEntries(zd.worlds.map((w) => [w.slug, { id: w.id, name: w.name }]));
const km = (v) => (v == null ? null : Math.round(v * 1000));

const routes = zd.routes
  .filter((r) => r.id != null)
  .map((r) => ({
    id: r.id,
    name: r.name,
    world_id: worlds[r.world]?.id ?? null,
    world: worlds[r.world]?.name ?? r.world,
    distance_m: km(r.distance),
    elevation_m: r.elevation ?? null,
    lead_in_m: km(r.leadInDistance) ?? 0,
    lead_in_free_ride_m: km(r.leadInDistanceFreeRide),
    lap: Boolean(r.lap),
    event_only: Boolean(r.eventOnly),
    sports: r.sports ?? [],
  }))
  .sort((a, b) => a.world.localeCompare(b.world) || a.name.localeCompare(b.name));

const out = {
  source: `zwift-data ${version} (MIT, Andi Pätzold)`,
  worlds: Object.fromEntries(zd.worlds.map((w) => [w.id, w.name])),
  routes,
};
const target = resolve("custom_components/zwift_map/data/routes.json");
writeFileSync(target, JSON.stringify(out, null, 1) + "\n");
console.log(`wrote ${routes.length} routes to ${target}`);
