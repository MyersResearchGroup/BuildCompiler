# Developer Guide for AI Agents

## 🧠 Mental Model

BuildCompiler is a **workflow orchestrator**.

Each function:
- Receives structured input
- Produces structured output
- Does not rely on hidden state

---

## 🔑 Core Entry Points

- `index_collections`
- `domestication`
- `assembly_lvl1`
- `assembly_lvl2`
- `transformation`
- `plating`
- `full_build`

---

## 📦 Contracts

Each function should:

INPUT:
- SBOL or JSON

OUTPUT:
- SBOL
- JSON
- Protocol files

---

## ⚠️ Constraints

- No hidden side effects
- Deterministic outputs
- Explicit file outputs

---

## 🧪 Testing Expectations

Each module must:
- Work independently
- Be testable with mock SBOL
- Validate outputs

---

## 🎯 Goals for Contributions

- Improve modularity
- Maintain pipeline clarity
- Avoid coupling biology logic with execution logic
