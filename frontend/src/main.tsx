import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './design/tokens.css';
import './design/base.css';
import { loadRuntimeConfig } from './api/config.ts';
import { App } from './app/App.tsx';

const container = document.getElementById('root');
if (!container) {
  throw new Error('Missing #root container');
}
const root = createRoot(container);

void loadRuntimeConfig().then((config) => {
  root.render(
    <StrictMode>
      <App config={config} />
    </StrictMode>,
  );
});
