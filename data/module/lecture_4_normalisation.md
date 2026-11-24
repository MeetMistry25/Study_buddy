# Lecture 4: Normalisation
topic: normalisation

## Slide 6
First normal form (1NF) requires that every attribute holds a single atomic value. Repeating groups and multi-valued attributes, such as a column storing a comma-separated list, break 1NF.

## Slide 8
A functional dependency X to Y means that each value of X determines exactly one value of Y. A dependency is partial when a non-key attribute depends on only part of a composite primary key.

## Slide 9
Second normal form (2NF) removes partial dependencies, so every non-key attribute depends on the whole of the primary key. Partial dependencies are removed in 2NF, and the table must already be in 1NF. Third normal form (3NF) builds on this by removing transitive dependencies.

## Slide 10
Third normal form (3NF) removes transitive dependencies, where a non-key attribute depends on another non-key attribute rather than directly on the key.

## Slide 11
Boyce-Codd normal form (BCNF) is stricter than 3NF: for every functional dependency X to Y, X must be a superkey. A table in 3NF can still violate BCNF when a non-key attribute determines part of a candidate key.

## Slide 12
A decomposition into smaller tables must be lossless, meaning that joining the new tables back together reproduces the original table with no spurious rows. A decomposition is lossless if the common attributes of the two new tables form a key of at least one of them.
