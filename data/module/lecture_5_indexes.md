# Lecture 5: Indexes
topic: indexes

## Slide 3
An index is a separate data structure that lets the database find rows without scanning the whole table. Indexes speed up reads but slow down inserts, updates and deletes because the index must also be maintained.

## Slide 5
Most relational databases use B-tree indexes by default. A B-tree index supports equality searches and range searches, such as BETWEEN, and keeps its keys in sorted order.

## Slide 6
A clustered index determines the physical order of rows in the table, so a table can have only one clustered index.

## Slide 7
A hash index supports only equality lookups. It cannot be used for range queries or for sorting.

## Slide 9
A composite index on (a, b) can be used by queries that filter on a, or on a and b, but generally not by queries that filter only on b. This is known as the leftmost prefix rule.

## Slide 10
Low-cardinality columns, such as a boolean flag, are usually poor candidates for a B-tree index because each value matches a large fraction of the table.
