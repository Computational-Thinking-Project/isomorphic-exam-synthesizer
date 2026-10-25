import { transformSync } from 'esbuild';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

/**
 * Node.js ESM loader hỗ trợ kiểm thử trực tiếp các file .jsx
 * và bỏ qua các file .css trong môi trường Node runner.
 */
export async function load(url, context, nextLoad) {
  if (url.endsWith('.css')) {
    return {
      format: 'module',
      shortCircuit: true,
      source: 'export default {};',
    };
  }

  if (url.endsWith('.jsx')) {
    const rawSource = fs.readFileSync(fileURLToPath(url), 'utf8');
    const { code } = transformSync(rawSource, {
      loader: 'jsx',
      jsx: 'automatic',
      format: 'esm',
      sourcefile: fileURLToPath(url),
    });
    return {
      format: 'module',
      shortCircuit: true,
      source: code,
    };
  }

  return nextLoad(url, context);
}
