import { SimOptions, WorldInfo } from '../types/flight';

/** Human-readable world label from /api/sim/options (falls back to the id). */
export function worldLabelFor(
  options: SimOptions | null | undefined,
  worldId: string | null | undefined,
): string {
  if (!worldId) return '';
  const match = options?.worlds.find((w: WorldInfo) => w.name === worldId);
  return match?.label ?? worldId.replace(/_/g, ' ');
}

export function defaultWorldFromOptions(options: SimOptions | null | undefined): string {
  if (options?.defaultWorld) return options.defaultWorld;
  return options?.worlds[0]?.name ?? '';
}
