import { mkdtempSync, readFileSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { fileURLToPath } from "node:url"
import { join, resolve } from "node:path"
import { spawnSync } from "node:child_process"

const scriptDir = fileURLToPath(new URL(".", import.meta.url))
const webRoot = resolve(scriptDir, "..")
const repoRoot = resolve(webRoot, "..")
const tempDir = mkdtempSync(join(tmpdir(), "context-engine-openapi-"))
const tempSchemaPath = join(tempDir, "openapi-schema.json")
const tempTypesPath = join(tempDir, "generated-api.ts")
const generatedTypesPath = join(webRoot, "src", "types", "generated-api.ts")
const openapiTypescriptCli = join(webRoot, "node_modules", "openapi-typescript", "bin", "cli.js")

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: webRoot,
    encoding: "utf8",
    stdio: "inherit",
    ...options,
  })
  if (result.status !== 0) {
    if (result.error) {
      throw result.error
    }
    throw new Error(`${command} ${args.join(" ")} failed with exit code ${result.status}`)
  }
}

function readNormalized(filePath) {
  return readFileSync(filePath, "utf8").replace(/\r\n/g, "\n")
}

try {
  run(process.env.PYTHON || "python", [join(repoRoot, "scripts", "export_openapi.py"), tempSchemaPath])
  run(process.execPath, [openapiTypescriptCli, tempSchemaPath, "-o", tempTypesPath])

  const expected = readNormalized(tempTypesPath)
  const current = readNormalized(generatedTypesPath)
  if (current !== expected) {
    console.error("OpenAPI generated TypeScript is out of date.")
    console.error("Run: npm.cmd run generate:api")
    process.exitCode = 1
  } else {
    console.log("OpenAPI generated TypeScript is up to date.")
  }
} finally {
  rmSync(tempDir, { recursive: true, force: true })
}
