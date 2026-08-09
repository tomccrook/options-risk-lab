import { Button } from "@base-ui/react/button";
import { Slider } from "@base-ui/react/slider";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { useEffect, useState, type ReactNode } from "react";
import type { Provenance } from "./api";
export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));
export function Action({
  children,
  onClick,
  disabled = false,
  pressed,
}: {
  children: ReactNode;
  onClick: () => void;
  disabled?: boolean;
  pressed?: boolean;
}) {
  return (
    <Button
      onClick={onClick}
      disabled={disabled}
      aria-pressed={pressed}
      className={cn(
        "rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:bg-slate-100 disabled:opacity-50",
        pressed && "border-teal-700 bg-teal-50 text-teal-900",
      )}
    >
      {children}
    </Button>
  );
}
export const fmt = (x: number | null | undefined, d = 4) =>
  x == null
    ? "Undefined"
    : x.toLocaleString("en-GB", {
        maximumFractionDigits: d,
        minimumFractionDigits: d,
      });
export function NumberControl({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  unit = "",
}: {
  label: string;
  value: number;
  onChange: (x: number) => void;
  min: number;
  max: number;
  step?: number;
  unit?: string;
}) {
  const [draft, setDraft] = useState(String(value));
  const [invalid, setInvalid] = useState(false);
  useEffect(() => {
    setDraft(String(value));
    setInvalid(false);
  }, [value]);
  const id = label.replace(/\W/g, "-");
  return (
    <div className="space-y-2">
      <label htmlFor={id} className="flex justify-between text-sm font-medium">
        {label}
        <span className="font-normal text-slate-600">{unit}</span>
      </label>
      <input
        id={id}
        type="number"
        value={draft}
        aria-invalid={invalid}
        aria-describedby={invalid ? `${id}-error` : undefined}
        min={min}
        max={max}
        step={step}
        onChange={(e) => {
          setDraft(e.currentTarget.value);
          const x = e.currentTarget.valueAsNumber;
          const valid = Number.isFinite(x) && x >= min && x <= max;
          setInvalid(!valid);
          if (valid) onChange(x);
        }}
        className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 tabular-nums"
      />
      {invalid ? (
        <p id={`${id}-error`} role="alert" className="text-xs text-red-800">
          Enter a number from {min} to {max} {unit}. The last valid value
          remains active.
        </p>
      ) : null}
      <Slider.Root
        value={value}
        min={min}
        max={max}
        step={step}
        onValueChange={(v) => onChange(typeof v === "number" ? v : v[0])}
      >
        <Slider.Control className="flex h-6 items-center">
          <Slider.Track className="relative h-1 w-full rounded bg-slate-200">
            <Slider.Indicator className="rounded bg-teal-700" />
            <Slider.Thumb
              aria-label={`${label} slider`}
              className="size-4 rounded-full border-2 border-teal-700 bg-white"
            />
          </Slider.Track>
        </Slider.Control>
      </Slider.Root>
    </div>
  );
}
export function Evidence({ value }: { value: Provenance }) {
  return (
    <details className="mt-6 border-t border-slate-200 pt-4 text-sm text-slate-600">
      <summary className="cursor-pointer font-medium text-slate-800">
        Calculation evidence & assumptions
      </summary>
      <dl className="mt-3 grid gap-2 break-all">
        <div>
          <dt>Basis</dt>
          <dd>
            {value.pricing_basis} · {value.quality}
          </dd>
        </div>
        <div>
          <dt>Assumptions</dt>
          <dd>
            {value.assumptions} · {value.valuation_clock}
          </dd>
        </div>
        <div>
          <dt>Configuration</dt>
          <dd className="font-mono text-xs">{value.config_hash}</dd>
        </div>
        <div>
          <dt>Source payload</dt>
          <dd className="font-mono text-xs">{value.source_sha256}</dd>
        </div>
        <div>
          <dt>Runtime packages</dt>
          <dd>
            {Object.entries(value.versions)
              .map(([k, v]) => `${k} ${v}`)
              .join(" · ")}
          </dd>
        </div>
        <div>
          <dt>Code / engine</dt>
          <dd className="font-mono text-xs">
            {value.code_revision} / {value.engine}
          </dd>
        </div>
      </dl>
    </details>
  );
}
export function Status({
  pending,
  error,
}: {
  pending: boolean;
  error?: string;
}) {
  return error ? (
    <p
      role="alert"
      className="rounded-md border border-red-300 bg-red-50 p-4 text-red-900"
    >
      Calculation unavailable: {error}
    </p>
  ) : pending ? (
    <div role="status" className="space-y-4">
      <p>Calculating with shared numerical service…</p>
      <div className="h-64 rounded bg-slate-100" />
    </div>
  ) : null;
}
