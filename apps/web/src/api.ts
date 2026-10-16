import { useEffect, useState } from "react";
import { z } from "zod";
export const greekSchema = z.object({
  price: z.number(),
  delta: z.number().nullable(),
  gamma: z.number().nullable(),
  vega: z.number().nullable(),
  theta: z.number().nullable(),
  rho: z.number().nullable(),
  vanna: z.number().nullable(),
  volga: z.number().nullable(),
  quality: z.string(),
});
export type Greeks = z.infer<typeof greekSchema>;
export const provenanceSchema = z.object({
  versions: z.record(z.string(), z.string()),
  source_sha256: z.string(),
  config_hash: z.string(),
  engine: z.string(),
  code_revision: z.string(),
  assumptions: z.string(),
  data: z.string(),
  units: z.record(z.string(), z.string()),
  pricing_basis: z.string(),
  quality: z.string(),
  valuation_clock: z.string(),
});
export type Provenance = z.infer<typeof provenanceSchema>;
export const curveSchema = z.object({
  rows: z.array(
    z.object({ x: z.number(), call: greekSchema, put: greekSchema }),
  ),
  selected: z.object({ call: greekSchema, put: greekSchema }),
  config: z.unknown(),
  provenance: provenanceSchema,
});
export function useService<T>(
  path: string,
  config: unknown,
  schema: z.ZodType<T>,
) {
  const key = JSON.stringify(config);
  const [state, setState] = useState<{
    data?: T;
    error?: string;
    pending: boolean;
  }>({ pending: true });
  useEffect(() => {
    const abort = new AbortController();
    let active = true;
    setState({ pending: true });
    const timer = setTimeout(async () => {
      try {
        const response = await fetch(path, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: key,
          signal: abort.signal,
        });
        if (!response.ok) {
          const error = await response.json();
          throw new Error(
            typeof error.detail === "string"
              ? error.detail
              : JSON.stringify(error.detail),
          );
        }
        const data = schema.parse(await response.json());
        if (active) setState({ data, pending: false });
      } catch (e) {
        if (active && !abort.signal.aborted)
          setState({
            pending: false,
            error: e instanceof Error ? e.message : "Calculation failed",
          });
      }
    }, 180);
    return () => {
      active = false;
      clearTimeout(timer);
      abort.abort();
    };
  }, [path, key, schema]);
  return state;
}
export const shockSchema = z.object({
  spot_return: z.number(),
  vol_change: z.number(),
  days: z.number(),
  skew_change: z.number(),
  term_change: z.number(),
  weight: z.number(),
});
export const scenarioSchema = z.object({
  shock: shockSchema,
  spot: z.number(),
  option_change: z.number(),
  share_change: z.number(),
  full_change: z.number(),
  approximation: z.number().nullable(),
  residual: z.number().nullable(),
  terms: z.record(z.string(), z.number()),
  quality: z.string(),
  basis: z.string(),
});
export const positionSchema = z.object({
  id: z.string(),
  quantity: z.number(),
  multiplier: z.number(),
  kind: z.string(),
  strike: z.number(),
  days: z.number(),
  assigned_iv: z.number(),
  quality: z.string(),
  price: z.number(),
  delta: z.number().nullable(),
  gamma: z.number().nullable(),
  vega: z.number().nullable(),
});
export const portfolioSchema = z.object({
  book: z.unknown(),
  risk: z.object({
    net: z.record(z.string(), z.number().nullable()),
    gross: z.record(z.string(), z.number()),
    positions: z.array(positionSchema),
    shares: z.number(),
    cash: z.number(),
    nav: z.number(),
    vega_per_vol_point: z.number(),
    return_scale_gamma: z.number(),
    total_surface_delta: z.number(),
    partial_basis: z.string(),
    quality: z.string(),
  }),
  selected: scenarioSchema,
  grid: z.array(scenarioSchema),
  config: z.unknown(),
  provenance: provenanceSchema,
});
const tradeSchema = z.object({
  id: z.string(),
  quantity: z.number(),
  mid: z.number(),
  multiplier: z.number(),
  instrument: z.unknown().optional(),
});
export const hedgeSchema = z.object({
  name: z.string(),
  status: z.string(),
  quantities: z.array(z.number()).optional(),
  fractional_control: z.array(z.number()).nullable().optional(),
  cost: z.number().optional(),
  financed_cost: z.number().optional(),
  capital: z.number().optional(),
  cvar: z.number().optional(),
  worst_loss: z.number().optional(),
  pnl: z.array(z.number()).optional(),
  residual: z.record(z.string(), z.number()).optional(),
  trades: z.array(tradeSchema).optional(),
});
export const comparisonSchema = z.object({
  frontier: z.array(
    z.object({
      cost: z.number(),
      cvar: z.number(),
      capital: z.number(),
      quantities: z.array(z.number()),
    }),
  ),
  hedges: z.array(hedgeSchema),
  candidates: z.array(z.unknown()),
  condition: z.number(),
  objective: z.string(),
  basis: z.string(),
  capital_basis: z.string(),
  limits: z.unknown(),
  weights: z.array(z.number()),
  config: z.unknown(),
  provenance: provenanceSchema,
});
export type Comparison = z.infer<typeof comparisonSchema>;
export const traceSchema = z.object({
  node: z.number(),
  days: z.number(),
  spot: z.number(),
  iv: z.number(),
  request: z.number(),
  fill: z.number(),
  execution_mid: z.number(),
  cost: z.number(),
  funding: z.number(),
  dividend: z.number(),
  shares: z.number(),
  cash: z.number(),
  option_value: z.number(),
  nav: z.number(),
  delta_before: z.number(),
  delta_after: z.number().nullable(),
});
export const replaySchema = z.object({
  distribution: z.array(z.object({ error_usd: z.number(), count: z.number() })),
  rejected_requests: z.array(z.number()),
  max_abs_delta: z.array(z.number()),
  delta_basis: z.string(),
  financed_error: z.array(z.number()),
  raw_pnl: z.array(z.number()),
  costs: z.array(z.number()),
  turnover: z.array(z.number()),
  trades: z.array(z.number()),
  trace: z.array(traceSchema),
  allocated: z.number(),
  funding_benchmark: z.number(),
  generator: z.string(),
  config: z.unknown(),
  quality: z.string(),
  metrics: z.record(z.string(), z.number()),
  provenance: provenanceSchema,
});
export const jobSchema = z.object({
  id: z.string(),
  status: z.enum(["queued", "running", "complete", "failed", "cancelled"]),
  manifest: z.unknown(),
  result: z.unknown().nullable(),
  error: z.string().nullable(),
});
export async function submit(path: string, config: unknown): Promise<string> {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (!r.ok) throw new Error(JSON.stringify(await r.json()));
  return z.object({ id: z.string() }).parse(await r.json()).id;
}

export const workbenchConfigSchema = z.object({
  case: z.string(),
  market: z.object({
    spot: z.number(),
    vol: z.number(),
    rate: z.number(),
    yield_: z.number(),
  }),
  surface: z.object({ motion: z.string() }),
  selected_shock: shockSchema,
  limits: z.object({
    cost_budget: z.number(),
    capital_budget: z.number(),
    share_half_spread: z.number(),
  }),
});
export const studyMetricSchema = z.object({
  target: z.string(),
  method: z.string(),
  seed: z.number().nullable(),
  split: z.string(),
  rmse: z.record(z.string(), z.number()),
  max_abs: z.record(z.string(), z.number()),
  bounds_failures: z.number(),
  shape_failures: z.number(),
  share_hedge_rmse_1_contract: z.number(),
  samples: z.number(),
  scenario_change_rmse_1_contract_usd: z.number().optional(),
  actual_share_hedge_pnl_discrepancy_rmse_usd: z.number().optional(),
  fallback_points: z.number().optional(),
});
export const studySchema = z.object({
  run_id: z.string(),
  metrics: z.array(studyMetricSchema),
  timings: z.array(
    z.object({
      target: z.string(),
      method: z.string(),
      seed: z.number().optional(),
      split: z.string().optional(),
      batch: z.number(),
      p50_ms: z.number(),
      p95_ms: z.number(),
    }),
  ),
  accepted: z.record(z.string(), z.boolean()),
  device: z.string(),
  dtype: z.string(),
  budget: z.string(),
  fallback: z.string(),
  provenance: provenanceSchema,
  generation: z.array(z.unknown()),
  reference_gate: z.object({ passed: z.boolean(), rows: z.array(z.unknown()) }),
});
export const probeSchema = z.object({
  input: z.unknown(),
  reference: z.array(z.number()),
  raw_surrogate: z.array(z.number()).nullable(),
  active: z.array(z.number()),
  engine: z.string(),
  reason: z.string(),
  total_ms: z.number(),
  quality: z.string(),
  reference_ms: z.number(),
  raw_inference_ms: z.number().nullable(),
  K: z.number(),
  units: z.array(z.string()),
  lifecycle: z.string(),
});

export const assetRowSchema = z.object({
  model: z.string(),
  label: z.string(),
  price: z.number(),
  delta: z.number(),
  gamma: z.number(),
  vega: z.number(),
  vega_basis: z.string(),
  parameters: z.record(z.string(), z.number()),
  reference_ms: z.number(),
});
export const assetComparisonSchema = z.object({
  rows: z.array(assetRowSchema),
  curves: z.array(z.record(z.string(), z.number())),
  scenarios: z.array(
    z.object({
      model: z.string(),
      spot_return: z.number(),
      days: z.number(),
      full_change: z.number(),
      spot_taylor: z.number(),
      residual: z.number(),
      basis: z.string(),
    }),
  ),
  numerical_checks: z.array(
    z.object({
      model: z.string(),
      reference: z.string(),
      price_error: z.number(),
      adaptive_refinements: z.number(),
    }),
  ),
  config: z.unknown(),
  total_ms: z.number(),
  basis: z.string(),
  warning: z.string(),
  provenance: provenanceSchema,
});
const mcEstimateSchema = z.object({
  value: z.number(),
  se: z.number(),
  ci95: z.array(z.number()),
  reference: z.number().optional(),
  error: z.number().optional(),
  spot_bump_usd: z.number().optional(),
});
export const mcComparisonSchema = z.object({
  config: z.unknown(),
  basis: z.string(),
  warning: z.string(),
  provenance: provenanceSchema,
  rows: z.array(
    z.object({
      model: z.string(),
      seed: z.number(),
      paths: z.number(),
      steps: z.number(),
      elapsed_ms: z.number(),
      greeks: z.object({
        price: mcEstimateSchema,
        delta: mcEstimateSchema,
        gamma: mcEstimateSchema,
        vega: mcEstimateSchema,
      }),
      gamma_bumps: z.array(mcEstimateSchema),
      discounted_spot: mcEstimateSchema,
      martingale_target: z.number(),
    }),
  ),
});
const assetSummarySchema = z.object({
  hedger: z.string(),
  rmse: z.number(),
  mean: z.number(),
  cvar95: z.number(),
  mean_cost: z.number(),
  mean_turnover: z.number(),
  rejected_requests: z.number(),
  max_abs_delta: z.number(),
});
const assetPairSchema = z.object({
  hedger: z.string(),
  baseline: z.string(),
  rmse_difference: z.number(),
  ci95: z.array(z.number()),
});
export const assetReplaySchema = z.object({
  parameters: z.record(z.string(), z.record(z.string(), z.number())),
  config: z.object({
    generator: z.string(),
    half_spread: z.number(),
    delay: z.number(),
    seed: z.number(),
    paths: z.number(),
    steps: z.number(),
    selected_hedger: z.string(),
    point: z.object({ spot: z.number(), strike: z.number(), tau: z.number() }),
  }),
  summary: z.array(assetSummarySchema),
  paired: z.array(assetPairSchema),
  trace: z.array(
    z.object({
      node: z.number(),
      days: z.number(),
      spot: z.number(),
      variance: z.number(),
      nav: z.number(),
      cash: z.number(),
      shares: z.number(),
      option_value: z.number(),
      request: z.number(),
      fill: z.number(),
      funding: z.number(),
      dividend: z.number(),
      cost: z.number(),
      delta_after: z.number().nullable(),
    }),
  ),
  distribution: z.array(z.object({ error_usd: z.number(), count: z.number() })),
  entry_premium_usd: z.number(),
  allocated: z.number(),
  funding_benchmark: z.number(),
  selected_hedger: z.string(),
  basis: z.string(),
  warning: z.string(),
  numerical_quality: z.object({ adaptive_refinements: z.number() }),
  provenance: provenanceSchema,
});
export const assetStudySchema = z.object({
  run_id: z.string(),
  protocol_sha256: z.string(),
  phase: z.string(),
  basis: z.string(),
  warning: z.string(),
  provenance: provenanceSchema,
  summary: z.array(
    assetSummarySchema.extend({
      generator: z.string(),
      spread: z.number(),
      delay: z.number(),
      mean_ci95: z.array(z.number()),
      cvar95_ci95: z.array(z.number()),
      tail_observations: z.number(),
    }),
  ),
  paired: z.array(
    assetPairSchema.extend({
      generator: z.string(),
      spread: z.number(),
      delay: z.number(),
      supports_threshold: z.boolean(),
      rmse_reduction_fraction: z.number(),
    }),
  ),
  episodes: z.object({
    rows: z.number(),
    sha256: z.string(),
    path: z.string(),
  }),
});

export function useRecordedJob<T>(schema: z.ZodType<T>, storageKey: string) {
  const [reload, setReload] = useState(0);
  const [id, setId] = useState("");
  const [savedId, setSavedId] = useState(() => {
    try {
      return localStorage.getItem(storageKey) ?? "";
    } catch {
      return "";
    }
  });
  const [job, setJob] = useState<ReturnType<typeof jobSchema.parse>>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!id) return;
    const abort = new AbortController();
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const response = await fetch(`/api/jobs/${id}`, {
          signal: abort.signal,
        });
        if (!response.ok)
          throw new Error(`Saved run unavailable (${response.status})`);
        const value = jobSchema.parse(await response.json());
        if (!active) return;
        setJob(value);
        if (value.status === "complete") {
          schema.parse(value.result);
          setBusy(false);
        } else if (value.status === "queued" || value.status === "running")
          timer = setTimeout(poll, 500);
        else {
          setError(value.error ?? `Run ${value.status}`);
          setBusy(false);
        }
      } catch (e) {
        if (active && !abort.signal.aborted) {
          setError(String(e));
          setBusy(false);
        }
      }
    }
    void poll();
    return () => {
      active = false;
      abort.abort();
      clearTimeout(timer);
    };
  }, [id, schema, reload]);
  const parsed =
    job?.status === "complete" ? schema.safeParse(job.result) : undefined;
  const data = parsed?.success ? parsed.data : undefined;
  function load(nextId: string) {
    setReload((v) => v + 1);
    setError("");
    setBusy(true);
    setJob(undefined);
    setId(nextId);
    setSavedId(nextId);
    try {
      localStorage.setItem(storageKey, nextId);
    } catch {
      /* Saving on server remains valid. */
    }
  }
  async function run(path: string, config: unknown) {
    setError("");
    setBusy(true);
    setJob(undefined);
    setId("");
    try {
      load(await submit(path, config));
    } catch (e) {
      setError(String(e));
      setBusy(false);
    }
  }
  async function cancel() {
    if (!id) return;
    try {
      await submit(`/api/jobs/${id}/cancel`, {});
    } catch (e) {
      setError(String(e));
    }
  }
  return {
    id,
    savedId,
    setSavedId,
    data,
    busy,
    error,
    run,
    load,
    cancel,
    manifest: job?.manifest,
  };
}
