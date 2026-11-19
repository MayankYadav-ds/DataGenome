// Keep framework telemetry disabled for every supported local startup command.
import { createRequire } from "node:module";
process.env.NEXT_TELEMETRY_DISABLED = "1";
const nextCLI = createRequire(import.meta.url);
nextCLI("next/dist/bin/next");
