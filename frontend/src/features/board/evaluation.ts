/** Evaluation formatting shared by the free board. Scores are White-relative. */

export function formatEvaluation(evalCp: number, mate: number | null): string {
  if (mate !== null) return `${mate < 0 ? '-' : ''}M${Math.abs(mate)}`;
  const pawns = evalCp / 100;
  return `${pawns >= 0 ? '+' : ''}${pawns.toFixed(2)}`;
}

/**
 * White's share of the evaluation bar, 0-100.
 * The logistic curve is the same one used for accuracy (Lichess).
 */
export function whiteShare(evalCp: number, mate: number | null): number {
  if (mate !== null) return mate > 0 ? 100 : 0;
  const capped = Math.max(-1000, Math.min(1000, evalCp));
  return 50 + 50 * (2 / (1 + Math.exp(-0.00368208 * capped)) - 1);
}
