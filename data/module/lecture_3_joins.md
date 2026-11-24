# Lecture 3: Joins
topic: joins

## Slide 3
An INNER JOIN returns only the rows where the join condition matches in both tables. Rows with no match in the other table are left out.

## Slide 5
A LEFT JOIN returns every row from the left table, together with the matching rows from the right table. Where there is no match, the columns from the right table are filled with NULL.

## Slide 6
A FULL OUTER JOIN returns all rows from both tables, filling in NULL where either side has no match.

## Slide 8
A CROSS JOIN returns the Cartesian product of two tables, pairing every row of the first table with every row of the second. If the tables have m and n rows, the result has m times n rows.

## Slide 10
A self join joins a table to itself using table aliases to tell the two copies apart. It is used for hierarchical data, such as employees and their managers.

## Slide 11
To find rows in the left table that have no match in the right table, use a LEFT JOIN and filter with WHERE on a right-table column IS NULL. This is known as the anti-join pattern.

## Slide 12
A WHERE filter on a right-table column in a LEFT JOIN removes the rows where that column is NULL, so the query behaves like an INNER JOIN. To keep the outer join behaviour, put the condition in the ON clause instead.
