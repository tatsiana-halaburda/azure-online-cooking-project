-- schemas for the three services
IF SCHEMA_ID(N'Tanya_Inventory') IS NULL EXEC(N'CREATE SCHEMA [Tanya_Inventory]');
IF SCHEMA_ID(N'Tanya_Ordering') IS NULL EXEC(N'CREATE SCHEMA [Tanya_Ordering]');
IF SCHEMA_ID(N'Tanya_Feedback') IS NULL EXEC(N'CREATE SCHEMA [Tanya_Feedback]');

