/**
 * Adapt the authoritative GrantResponse for the existing query budget view.
 * The browser deliberately does not recompute remaining epsilon.
 */
export function grantBudgetSnapshot(grant) {
  if (!grant) return null;
  return {
    budget_id: grant.grant_id,
    source: "grant",
    total_epsilon: grant.total_epsilon_limit,
    used_epsilon: grant.epsilon_consumed,
    reserved_epsilon: grant.epsilon_reserved,
    remaining_epsilon: grant.epsilon_remaining,
  };
}
