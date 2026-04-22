-- Tanya_Inventory tables
IF OBJECT_ID(N'[Tanya_Inventory].[Warehouses]', N'U') IS NULL
BEGIN
  CREATE TABLE [Tanya_Inventory].[Warehouses] (
    [WarehouseId] UNIQUEIDENTIFIER NOT NULL CONSTRAINT [PK_TanyaInventory_Warehouses] PRIMARY KEY,
    [Name] NVARCHAR(200) NOT NULL,
    [Location] NVARCHAR(300) NOT NULL,
    [IsActive] BIT NOT NULL CONSTRAINT [DF_TanyaInventory_Warehouses_IsActive] DEFAULT (1)
  );
END

IF OBJECT_ID(N'[Tanya_Inventory].[Ingredients]', N'U') IS NULL
BEGIN
  CREATE TABLE [Tanya_Inventory].[Ingredients] (
    [IngredientId] UNIQUEIDENTIFIER NOT NULL CONSTRAINT [PK_TanyaInventory_Ingredients] PRIMARY KEY,
    [Name] NVARCHAR(200) NOT NULL,
    [Category] NVARCHAR(100) NOT NULL,
    [Unit] NVARCHAR(50) NOT NULL,
    [ReorderLevel] DECIMAL(10,2) NOT NULL,
    [IsActive] BIT NOT NULL CONSTRAINT [DF_TanyaInventory_Ingredients_IsActive] DEFAULT (1)
  );

  ALTER TABLE [Tanya_Inventory].[Ingredients]
    ADD CONSTRAINT [UQ_TanyaInventory_Ingredients_Name] UNIQUE ([Name]);
END

IF OBJECT_ID(N'[Tanya_Inventory].[Stock]', N'U') IS NULL
BEGIN
  CREATE TABLE [Tanya_Inventory].[Stock] (
    [StockId] UNIQUEIDENTIFIER NOT NULL CONSTRAINT [PK_TanyaInventory_Stock] PRIMARY KEY,
    [IngredientId] UNIQUEIDENTIFIER NOT NULL,
    [WarehouseId] UNIQUEIDENTIFIER NOT NULL,
    [Quantity] DECIMAL(10,2) NOT NULL,
    [ExpirationDate] DATE NULL,
    CONSTRAINT [CK_TanyaInventory_Stock_QuantityNonNegative] CHECK ([Quantity] >= 0)
  );

  ALTER TABLE [Tanya_Inventory].[Stock]
    ADD CONSTRAINT [FK_TanyaInventory_Stock_Ingredients]
    FOREIGN KEY ([IngredientId]) REFERENCES [Tanya_Inventory].[Ingredients]([IngredientId]);

  ALTER TABLE [Tanya_Inventory].[Stock]
    ADD CONSTRAINT [FK_TanyaInventory_Stock_Warehouses]
    FOREIGN KEY ([WarehouseId]) REFERENCES [Tanya_Inventory].[Warehouses]([WarehouseId]);
END

