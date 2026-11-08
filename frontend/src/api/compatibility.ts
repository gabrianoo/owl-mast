import manifest from '../../api-compatibility.json';

/**
 * API compatibility policy (docs/api-compatibility.md). The backend publishes the contract it
 * implements at `GET {apiPathPrefix}/compatibility`; this frontend declares the contract it
 * supports in `api-compatibility.json`. A pair is compatible when the majors are equal and the
 * backend minor is at least the frontend's required minimum (minor versions only add).
 */
export interface ApiContractVersion {
  major: number;
  minor: number;
}

export interface CompatibilityDescriptor {
  service: string;
  backendVersion: string;
  apiContract: ApiContractVersion;
}

export interface SupportedContract {
  major: number;
  minMinor: number;
}

export const FRONTEND_VERSION: string = manifest.frontendVersion;
export const SUPPORTED_CONTRACT: SupportedContract = manifest.supportedApiContract;
export const DESCRIPTOR_PATH: string = manifest.descriptorPath;

export type CompatibilityVerdict =
  | { verdict: 'compatible'; backend: ApiContractVersion; supported: SupportedContract }
  | { verdict: 'incompatible'; backend: ApiContractVersion; supported: SupportedContract; reason: string };

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0;
}

export function parseDescriptor(body: unknown): CompatibilityDescriptor {
  if (typeof body !== 'object' || body === null) {
    throw new Error('descriptor is not an object');
  }
  const record = body as Record<string, unknown>;
  const contract = record.apiContract;
  if (typeof record.service !== 'string' || typeof record.backendVersion !== 'string') {
    throw new Error('descriptor is missing service or backendVersion');
  }
  if (typeof contract !== 'object' || contract === null) {
    throw new Error('descriptor is missing apiContract');
  }
  const { major, minor } = contract as Record<string, unknown>;
  if (!isNonNegativeInteger(major) || !isNonNegativeInteger(minor)) {
    throw new Error('apiContract major/minor must be non-negative integers');
  }
  return { service: record.service, backendVersion: record.backendVersion, apiContract: { major, minor } };
}

export function evaluateCompatibility(backend: ApiContractVersion, supported: SupportedContract = SUPPORTED_CONTRACT): CompatibilityVerdict {
  if (backend.major !== supported.major) {
    return {
      verdict: 'incompatible',
      backend,
      supported,
      reason: `This frontend supports API contract ${supported.major}.x (at least ${supported.major}.${supported.minMinor}); the backend publishes ${formatContract(backend)}.`,
    };
  }
  if (backend.minor < supported.minMinor) {
    return {
      verdict: 'incompatible',
      backend,
      supported,
      reason: `This frontend needs at least API contract ${supported.major}.${supported.minMinor}; the backend publishes ${formatContract(backend)}.`,
    };
  }
  return { verdict: 'compatible', backend, supported };
}

export function formatContract(contract: ApiContractVersion): string {
  return `${contract.major}.${contract.minor}`;
}

export function descriptorsEqual(a: CompatibilityDescriptor, b: CompatibilityDescriptor): boolean {
  return (
    a.service === b.service &&
    a.backendVersion === b.backendVersion &&
    a.apiContract.major === b.apiContract.major &&
    a.apiContract.minor === b.apiContract.minor
  );
}
