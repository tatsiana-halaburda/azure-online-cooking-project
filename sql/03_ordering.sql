-- Tanya_Ordering tables
IF OBJECT_ID(N'[Tanya_Ordering].[Orders]', N'U') IS NULL
BEGIN
  CREATE TABLE [Tanya_Ordering].[Orders] (
    [OrderId] UNIQUEIDENTIFIER NOT NULL CONSTRAINT [PK_TanyaOrdering_Orders] PRIMARY KEY,
    [Status] NVARCHAR(50) NOT NULL,
    [CreatedAt] DATETIME2 NOT NULL,
    [TotalCost] DECIMAL(18,2) NOT NULL,
    [Notes] NVARCHAR(500) NULL
  );
END

IF OBJECT_ID(N'[Tanya_Ordering].[OrderItems]', N'U') IS NULL
BEGIN
  CREATE TABLE [Tanya_Ordering].[OrderItems] (
    [OrderItemId] UNIQUEIDENTIFIER NOT NULL CONSTRAINT [PK_TanyaOrdering_OrderItems] PRIMARY KEY,
    [OrderId] UNIQUEIDENTIFIER NOT NULL,
    [IngredientId] UNIQUEIDENTIFIER NOT NULL,
    [Quantity] DECIMAL(10,2) NOT NULL,
    [UnitPrice] DECIMAL(10,2) NOT NULL
  );

  ALTER TABLE [Tanya_Ordering].[OrderItems]
    ADD CONSTRAINT [FK_TanyaOrdering_OrderItems_Orders]
    FOREIGN KEY ([OrderId]) REFERENCES [Tanya_Ordering].[Orders]([OrderId]);
END

IF OBJECT_ID(N'[Tanya_Ordering].[StockReservations]', N'U') IS NULL
BEGIN
  CREATE TABLE [Tanya_Ordering].[StockReservations] (
    [ReservationId] UNIQUEIDENTIFIER NOT NULL CONSTRAINT [PK_TanyaOrdering_StockReservations] PRIMARY KEY,
    [OrderId] UNIQUEIDENTIFIER NOT NULL,
    [IngredientId] UNIQUEIDENTIFIER NOT NULL,
    [ReservedQty] DECIMAL(10,2) NOT NULL,
    [Status] NVARCHAR(50) NOT NULL
  );

  ALTER TABLE [Tanya_Ordering].[StockReservations]
    ADD CONSTRAINT [FK_TanyaOrdering_StockReservations_Orders]
    FOREIGN KEY ([OrderId]) REFERENCES [Tanya_Ordering].[Orders]([OrderId]);
END

