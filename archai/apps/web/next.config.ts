import type { NextConfig } from 'next';
import path from 'node:path';
import { PHASE_DEVELOPMENT_SERVER } from 'next/constants';

export default function config(phase: string): NextConfig {
  return {
    reactStrictMode: true,
    basePath: '/design',
    distDir: phase === PHASE_DEVELOPMENT_SERVER ? '.next-dev' : '.next',
    outputFileTracingRoot: path.join(process.cwd(), '../..'),
  };
}
