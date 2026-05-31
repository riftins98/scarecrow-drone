import { SimOptions, SpawnMap } from '../types/flight';

export function spawnMapForWorld(
  options: SimOptions | null | undefined,
  world: string | null | undefined,
): SpawnMap | null {
  if (!options || !world) return null;

  const worldInfo = options.worlds.find((w) => w.name === world);
  if (worldInfo?.spawn) return worldInfo.spawn;

  const indexed = options.spawnMaps?.[world];
  if (indexed) return indexed;

  if (options.spawnWorld === world && options.spawnBounds) {
    return {
      world,
      wallBounds: options.spawnBounds,
      bounds: options.spawnBounds,
      obstacles: options.spawnObstacles ?? [],
      obstacleMargin: options.spawnObstacleMargin ?? 0,
      wallMargin: 0,
    };
  }

  return null;
}
