# Adapter contract

An Adapter supplies project facts:

- stable tracked project identity and runtime-derived checkout identity;
- detected stack markers;
- candidate verification commands;
- approved document authority;
- enabled generic packs and Lens IDs;
- local state root;
- explicit side-effect approvals.

An Adapter does not copy Lens questions, select models, add permissions, or redefine core safety. Static detection may propose a profile but cannot approve it.

Keep the default adapter `generic-repo`. Add a stack or project adapter only after a concrete unsupported case and regression fixture exist.

## User-defined documentation provider

The default is the managed Markdown system. A project may instead declare:

```json
{
  "documentation": {
    "provider": "custom",
    "entrypoint": ".maestro/adapters/team-docs.md",
    "core_documents": {
      "project": "docs/project.md",
      "architecture": "docs/architecture.md"
    },
    "external_topics": {},
    "custom_adapter": {
      "id": "team-docs",
      "instructions_path": ".maestro/adapters/team-docs.md"
    }
  }
}
```

The instruction file is project-owned and repository-local. It tells the host how to select documents and return `maestro_docs_selection_v1`. Core validates the pointer and returns a handoff; it does not execute a command, ship a provider implementation, synchronize external data, or weaken authority and approval rules.
