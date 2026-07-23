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
