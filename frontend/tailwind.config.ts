import type { Config } from "tailwindcss";
import { planGeneratorThemeExtend } from "./tailwind.config.additions";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: { extend: { ...planGeneratorThemeExtend } },
} satisfies Config;
