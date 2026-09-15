# Conflict review patterns

Read this file before a large or refactor-coupled merge conflict.

## Refactor and feature work

One branch can replace an interface while the other adds behavior through the old interface. Keep the replacement interface. Port the new behavior to it. Then check every caller and test.

## Migration collision

Two branches can add migrations with the same identifier or incompatible order. Resolve the ordering before you merge runtime code. Check that the migration names, dependencies, and schema assumptions are unique and coherent.

## Removed data model

One branch can remove a table, field, join, or document layer while the other branch adds a feature on it. Keep the current model. Rebuild the feature on the current model. Search for old fields and joins after the textual merge.

## Clean merge with contract drift

A merge can finish without conflict markers but still combine incompatible APIs. Compare changed public functions, configuration keys, schemas, and tests. Use targeted searches for retired names. Correct the drift before you save the merge.
