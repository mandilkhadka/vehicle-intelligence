import nextCoreWebVitals from "eslint-config-next/core-web-vitals"
import nextTypescript from "eslint-config-next/typescript"

const ignores = {
  ignores: [
    ".next/**",
    "coverage/**",
    "next-env.d.ts",
    "node_modules/**",
  ],
}

const projectRules = {
  rules: {
    "@typescript-eslint/no-explicit-any": "off",
    "@typescript-eslint/no-require-imports": "off",
    "react-hooks/set-state-in-effect": "off",
  },
}

const config = [
  ...nextCoreWebVitals,
  ...nextTypescript,
  projectRules,
  ignores,
]

export default config
