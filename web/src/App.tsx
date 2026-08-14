import { useReducer } from "react";
import { copy } from "./copy";
import { initialState, reduce } from "./state";

export function App() {
  const [state] = useReducer(reduce, undefined, initialState);
  return (
    <div>
      <header>
        <h1>{copy.title}</h1>
        <p>{copy.subtitle}</p>
        <p>{state.phase}</p>
      </header>
      <p>{copy.attribution}</p>
    </div>
  );
}
