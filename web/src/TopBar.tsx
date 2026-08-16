import type { Dispatch } from "react";
import { copy } from "./copy";
import type { Action, AppState } from "./types";

type Props = {
  state: AppState;
  dispatch: Dispatch<Action>;
  night: boolean;
};

export function TopBar({ state, dispatch, night }: Props) {
  return (
    <header className="topbar">
      <div className="topbar-titles">
        <h1>
          {copy.title}
          {night ? <span className="night-badge">{copy.nightBadge}</span> : null}
        </h1>
        <p className="subtitle">{copy.subtitle}</p>
      </div>
      <label className="datetime">
        <span className="sr-only">日時</span>
        <input
          type="datetime-local"
          value={state.datetimeLocal}
          onChange={(e) =>
            dispatch({ type: "SET_DATETIME", value: e.target.value })
          }
        />
      </label>
    </header>
  );
}
