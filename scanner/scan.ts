#!/usr/bin/env node
/**
 * dupescan: near-duplicate detection with MinHash and LSH banding.
 *
 * Pipeline per document:
 *   normalise -> 5-word shingles -> 64 MinHash values -> 16 bands of 4 rows.
 *
 * Banding turns "compare every pair" into "compare documents that agree on one
 * band", which is what makes 20,000 documents tractable. Every candidate pair is
 * then verified with an exact Jaccard over the shingle sets, so the reported
 * similarity is measured, not estimated.
 *
 * Usage: node --experimental-strip-types scan.ts --docs data/docs.jsonl --out data/pairs.json
 */

import { readFileSync, writeFileSync } from "node:fs";

const SHINGLE = 5;
const HASHES = 64;
const BANDS = 16;
const ROWS = HASHES / BANDS;
const MOD = 0x7fffffff;
const THRESHOLD = 0.85;

type Doc = { id: string; text: string };
type Pair = { a: string; b: string; jaccard: number };

function murmur3(input: string, seed: number): number {
  let h = seed >>> 0;
  const len = input.length;
  let i = 0;
  while (i + 4 <= len) {
    let k =
      (input.charCodeAt(i) & 0xff) |
      ((input.charCodeAt(i + 1) & 0xff) << 8) |
      ((input.charCodeAt(i + 2) & 0xff) << 16) |
      ((input.charCodeAt(i + 3) & 0xff) << 24);
    k = Math.imul(k, 0xcc9e2d51);
    k = (k << 15) | (k >>> 17);
    k = Math.imul(k, 0x1b873593);
    h ^= k;
    h = (h << 13) | (h >>> 19);
    h = (Math.imul(h, 5) + 0xe6546b64) | 0;
    i += 4;
  }
  let tail = 0;
  switch (len & 3) {
    case 3:
      tail ^= (input.charCodeAt(i + 2) & 0xff) << 16;
    /* falls through */
    case 2:
      tail ^= (input.charCodeAt(i + 1) & 0xff) << 8;
    /* falls through */
    case 1:
      tail ^= input.charCodeAt(i) & 0xff;
      tail = Math.imul(tail, 0xcc9e2d51);
      tail = (tail << 15) | (tail >>> 17);
      tail = Math.imul(tail, 0x1b873593);
      h ^= tail;
  }
  h ^= len;
  h ^= h >>> 16;
  h = Math.imul(h, 0x85ebca6b);
  h ^= h >>> 13;
  h = Math.imul(h, 0xc2b2ae35);
  h ^= h >>> 16;
  return h >>> 0;
}

function tokens(text: string): string[] {
  return text.toLowerCase().match(/[a-z0-9']+/g) ?? [];
}

function shingleHashes(text: string): Set<number> {
  const words = tokens(text);
  const hashes = new Set<number>();
  if (words.length === 0) {
    return hashes;
  }
  if (words.length <= SHINGLE) {
    hashes.add(murmur3(words.join(" "), 0x9e3779b1));
    return hashes;
  }
  for (let i = 0; i + SHINGLE <= words.length; i++) {
    hashes.add(murmur3(words.slice(i, i + SHINGLE).join(" "), 0x9e3779b1));
  }
  return hashes;
}

function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const random = mulberry32(42);
const COEFFICIENTS = Array.from({ length: HASHES }, () => ({
  a: 1 + Math.floor(random() * (MOD - 1)),
  b: Math.floor(random() * MOD),
}));

function signature(shingles: Set<number>): Uint32Array {
  const sig = new Uint32Array(HASHES).fill(0xffffffff);
  for (const hash of shingles) {
    for (let i = 0; i < HASHES; i++) {
      const value = ((COEFFICIENTS[i].a * hash + COEFFICIENTS[i].b) % MOD) >>> 0;
      if (value < sig[i]) {
        sig[i] = value;
      }
    }
  }
  return sig;
}

function jaccard(a: Set<number>, b: Set<number>): number {
  let intersection = 0;
  const [small, large] = a.size <= b.size ? [a, b] : [b, a];
  for (const value of small) {
    if (large.has(value)) {
      intersection += 1;
    }
  }
  const union = a.size + b.size - intersection;
  return union === 0 ? 0 : intersection / union;
}

function exactKey(text: string): string {
  return tokens(text).join(" ");
}

function parseArgs(argv: string[]): Record<string, string> {
  const args: Record<string, string> = {};
  for (let i = 0; i < argv.length; i++) {
    if (!argv[i].startsWith("--")) continue;
    const next = argv[i + 1];
    if (next !== undefined && !next.startsWith("--")) {
      args[argv[i].slice(2)] = next;
      i += 1;
    } else {
      args[argv[i].slice(2)] = "true";
    }
  }
  return args;
}

const args = parseArgs(process.argv.slice(2));
const docsPath = args.docs ?? "data/docs.jsonl";
const outPath = args.out ?? "data/pairs.json";
const exactOnly = args.exact === "true";
const threshold = Number(args.threshold ?? THRESHOLD);

const started = process.hrtime.bigint();
const lines = readFileSync(docsPath, "utf8").split("\n");
const docs: Doc[] = [];
for (const line of lines) {
  const trimmed = line.trim();
  if (!trimmed) continue;
  try {
    const parsed = JSON.parse(trimmed) as Doc;
    if (parsed && typeof parsed.id === "string" && typeof parsed.text === "string") {
      docs.push(parsed);
    }
  } catch {
    // Skip malformed lines rather than failing the whole run.
  }
}

const pairs: Pair[] = [];
if (exactOnly) {
  const buckets = new Map<string, string[]>();
  for (const doc of docs) {
    const key = exactKey(doc.text);
    const bucket = buckets.get(key);
    if (bucket) bucket.push(doc.id);
    else buckets.set(key, [doc.id]);
  }
  for (const ids of buckets.values()) {
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        pairs.push({ a: ids[i], b: ids[j], jaccard: 1 });
      }
    }
  }
} else {
  const shingles: Set<number>[] = [];
  const signatures: Uint32Array[] = [];
  for (const doc of docs) {
    const set = shingleHashes(doc.text);
    shingles.push(set);
    signatures.push(signature(set));
  }

  const buckets = new Map<string, number[]>();
  for (let index = 0; index < docs.length; index++) {
    for (let band = 0; band < BANDS; band++) {
      const slice = Array.from(
        signatures[index].subarray(band * ROWS, band * ROWS + ROWS),
      ).join(",");
      const key = band + ":" + slice;
      const bucket = buckets.get(key);
      if (bucket) bucket.push(index);
      else buckets.set(key, [index]);
    }
  }

  const seen = new Set<string>();
  for (const bucket of buckets.values()) {
    if (bucket.length < 2) continue;
    for (let i = 0; i < bucket.length; i++) {
      for (let j = i + 1; j < bucket.length; j++) {
        const first = Math.min(bucket[i], bucket[j]);
        const second = Math.max(bucket[i], bucket[j]);
        const key = first + ":" + second;
        if (seen.has(key)) continue;
        seen.add(key);
        const score = jaccard(shingles[first], shingles[second]);
        if (score >= threshold) {
          pairs.push({ a: docs[first].id, b: docs[second].id, jaccard: Number(score.toFixed(4)) });
        }
      }
    }
  }
}

pairs.sort((x, y) => (x.a < y.a ? -1 : x.a > y.a ? 1 : x.b < y.b ? -1 : 1));
const elapsed = Number(process.hrtime.bigint() - started) / 1e9;
writeFileSync(
  outPath,
  JSON.stringify(
    {
      schema_version: 1,
      method: exactOnly ? "exact" : "minhash-lsh",
      threshold,
      hashes: HASHES,
      bands: BANDS,
      docs: docs.length,
      pairs: pairs.length,
      elapsed_s: Number(elapsed.toFixed(3)),
      docs_per_s: Math.round(docs.length / Math.max(elapsed, 1e-9)),
      matches: pairs,
    },
    null,
  ),
);
console.log(
  `${exactOnly ? "exact" : "minhash"}: ${docs.length} docs, ${pairs.length} pairs, ` +
    `${elapsed.toFixed(2)} s (${Math.round(docs.length / Math.max(elapsed, 1e-9))} docs/s)`,
);
