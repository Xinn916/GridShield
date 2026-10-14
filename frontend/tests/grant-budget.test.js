import assert from "node:assert/strict";
import test from "node:test";
import { grantBudgetSnapshot } from "../src/query/grant-budget.js";

test("Grant budget snapshot uses the server remaining value", async () => {
  const grant = {
    grant_id: "GRANT-A",
    total_epsilon_limit: 20,
    epsilon_consumed: 4,
    epsilon_reserved: 1,
    epsilon_remaining: 15,
  };
  const budget = grantBudgetSnapshot(grant);
  assert.deepEqual(budget, {
    budget_id: "GRANT-A",
    source: "grant",
    total_epsilon: 20,
    used_epsilon: 4,
    reserved_epsilon: 1,
    remaining_epsilon: 15,
  });
  assert.equal(budget.remaining_epsilon, grant.epsilon_remaining);
});

test("switching Grants cannot carry the previous budget fields", () => {
  const first = grantBudgetSnapshot({
    grant_id: "GRANT-A",
    total_epsilon_limit: 20,
    epsilon_consumed: 4,
    epsilon_reserved: 0,
    epsilon_remaining: 16,
  });
  const second = grantBudgetSnapshot({
    grant_id: "GRANT-B",
    total_epsilon_limit: 20,
    epsilon_consumed: 1,
    epsilon_reserved: 0,
    epsilon_remaining: 19,
  });
  assert.equal(first.remaining_epsilon, 16);
  assert.equal(second.remaining_epsilon, 19);
  assert.notEqual(first.budget_id, second.budget_id);
});
