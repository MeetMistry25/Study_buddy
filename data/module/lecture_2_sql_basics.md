# Lecture 2: SQL basics
topic: sql_basics

## Slide 4
The SELECT statement retrieves rows from a table. The WHERE clause filters individual rows before any grouping takes place.

## Slide 6
GROUP BY groups rows that share values so that aggregate functions such as COUNT, SUM and AVG can be applied to each group. The HAVING clause filters groups after aggregation, whereas WHERE filters individual rows before aggregation.

## Slide 7
ORDER BY sorts the result set. The default order is ascending (ASC), and DESC reverses it.

## Slide 9
The DISTINCT keyword removes duplicate rows from the result set. COUNT(*) counts all rows, while COUNT(column) ignores NULL values in that column.
