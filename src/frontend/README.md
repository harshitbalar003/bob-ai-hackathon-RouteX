# Supply Chain Disruption Assistant — Frontend

React 18 + TypeScript + Vite application for the control-tower operator interface.

## Layout

```
src/
  components/    UI primitives and feature components
  data/fixtures/ Static mock data (JSON)
  lib/           Adapter layer, utilities, store
  pages/         Route-level page components
  types/         Domain type definitions
  test/          Test setup and utilities
```

## Running

```sh
npm install
npm run dev        # VITE_DATA_SOURCE=mock by default
```

## Environment

Copy `../.env.example` to `.env.local` for overrides. See `.env.example` for all variables.

## Tests

```sh
npm run test
```
