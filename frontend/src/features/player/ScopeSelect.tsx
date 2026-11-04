import { useId } from 'react';

import type { Scope, TimeClass } from '../../types/api';
import { PERIOD_OPTIONS, TIME_CLASS_OPTIONS } from './scope';

const SELECT =
  'appearance-none rounded-lg border border-white/10 bg-board-850 py-1.5 pl-3 pr-8 text-xs text-chalk-100';

function Chevron() {
  return (
    <span
      aria-hidden="true"
      className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[10px] text-chalk-500"
    >
      ▾
    </span>
  );
}

export function ScopeSelect({
  scope,
  onChange,
}: {
  scope: Scope;
  onChange: (scope: Scope) => void;
}) {
  const classId = useId();
  const periodId = useId();
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-chalk-400">
      <div className="flex items-center gap-2">
        <label htmlFor={classId}>Time class</label>
        <div className="relative">
          <select
            id={classId}
            value={scope.timeClass}
            onChange={(event) => onChange({ ...scope, timeClass: event.target.value as TimeClass })}
            className={SELECT}
          >
            {TIME_CLASS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <Chevron />
        </div>
      </div>
      <div className="flex items-center gap-2">
        <label htmlFor={periodId}>Period</label>
        <div className="relative">
          <select
            id={periodId}
            value={scope.days}
            onChange={(event) => onChange({ ...scope, days: Number(event.target.value) })}
            className={SELECT}
          >
            {PERIOD_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <Chevron />
        </div>
      </div>
    </div>
  );
}
