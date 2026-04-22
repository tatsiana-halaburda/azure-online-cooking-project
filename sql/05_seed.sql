-- demo seed (ingredient ids line up across schemas)
DECLARE @wh_main UNIQUEIDENTIFIER = '11111111-1111-1111-1111-111111111111';
DECLARE @wh_backup UNIQUEIDENTIFIER = '22222222-2222-2222-2222-222222222222';

DECLARE @ing_salt UNIQUEIDENTIFIER = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
DECLARE @ing_milk UNIQUEIDENTIFIER = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
DECLARE @ing_flour UNIQUEIDENTIFIER = 'cccccccc-cccc-cccc-cccc-cccccccccccc';

DECLARE @order_1 UNIQUEIDENTIFIER = '33333333-3333-3333-3333-333333333333';
DECLARE @order_2 UNIQUEIDENTIFIER = '44444444-4444-4444-4444-444444444444';

DECLARE @order_item_1 UNIQUEIDENTIFIER = '55555555-5555-5555-5555-555555555555';
DECLARE @order_item_2 UNIQUEIDENTIFIER = '66666666-6666-6666-6666-666666666666';
DECLARE @order_item_3 UNIQUEIDENTIFIER = '77777777-7777-7777-7777-777777777777';

DECLARE @res_1 UNIQUEIDENTIFIER = '88888888-8888-8888-8888-888888888888';
DECLARE @res_2 UNIQUEIDENTIFIER = '99999999-9999-9999-9999-999999999999';

DECLARE @fb_1 UNIQUEIDENTIFIER = '12121212-1212-1212-1212-121212121212';
DECLARE @fb_2 UNIQUEIDENTIFIER = '13131313-1313-1313-1313-131313131313';
DECLARE @fb_3 UNIQUEIDENTIFIER = '14141414-1414-1414-1414-141414141414';

DECLARE @sum_salt UNIQUEIDENTIFIER = '15151515-1515-1515-1515-151515151515';
DECLARE @sum_milk UNIQUEIDENTIFIER = '16161616-1616-1616-1616-161616161616';

-- Inventory
IF NOT EXISTS (SELECT 1 FROM [Tanya_Inventory].[Warehouses] WHERE [WarehouseId] = @wh_main)
  INSERT INTO [Tanya_Inventory].[Warehouses] ([WarehouseId], [Name], [Location], [IsActive])
  VALUES (@wh_main, N'Main Warehouse', N'Toronto, ON', 1);

IF NOT EXISTS (SELECT 1 FROM [Tanya_Inventory].[Warehouses] WHERE [WarehouseId] = @wh_backup)
  INSERT INTO [Tanya_Inventory].[Warehouses] ([WarehouseId], [Name], [Location], [IsActive])
  VALUES (@wh_backup, N'Backup Warehouse', N'Ottawa, ON', 1);

IF NOT EXISTS (SELECT 1 FROM [Tanya_Inventory].[Ingredients] WHERE [IngredientId] = @ing_salt)
  INSERT INTO [Tanya_Inventory].[Ingredients] ([IngredientId], [Name], [Category], [Unit], [ReorderLevel], [IsActive])
  VALUES (@ing_salt, N'Salt', N'Spice', N'kg', 5.00, 1);

IF NOT EXISTS (SELECT 1 FROM [Tanya_Inventory].[Ingredients] WHERE [IngredientId] = @ing_milk)
  INSERT INTO [Tanya_Inventory].[Ingredients] ([IngredientId], [Name], [Category], [Unit], [ReorderLevel], [IsActive])
  VALUES (@ing_milk, N'Milk', N'Dairy', N'litre', 30.00, 1);

IF NOT EXISTS (SELECT 1 FROM [Tanya_Inventory].[Ingredients] WHERE [IngredientId] = @ing_flour)
  INSERT INTO [Tanya_Inventory].[Ingredients] ([IngredientId], [Name], [Category], [Unit], [ReorderLevel], [IsActive])
  VALUES (@ing_flour, N'Flour', N'Grain', N'kg', 20.00, 1);

IF NOT EXISTS (SELECT 1 FROM [Tanya_Inventory].[Stock] WHERE [StockId] = 'aaaaaaaa-0000-0000-0000-000000000001')
  INSERT INTO [Tanya_Inventory].[Stock] ([StockId], [IngredientId], [WarehouseId], [Quantity], [ExpirationDate])
  VALUES ('aaaaaaaa-0000-0000-0000-000000000001', @ing_salt, @wh_main, 12.50, NULL);

IF NOT EXISTS (SELECT 1 FROM [Tanya_Inventory].[Stock] WHERE [StockId] = 'bbbbbbbb-0000-0000-0000-000000000002')
  INSERT INTO [Tanya_Inventory].[Stock] ([StockId], [IngredientId], [WarehouseId], [Quantity], [ExpirationDate])
  VALUES ('bbbbbbbb-0000-0000-0000-000000000002', @ing_milk, @wh_main, 18.00, '2026-06-01');

IF NOT EXISTS (SELECT 1 FROM [Tanya_Inventory].[Stock] WHERE [StockId] = 'cccccccc-0000-0000-0000-000000000003')
  INSERT INTO [Tanya_Inventory].[Stock] ([StockId], [IngredientId], [WarehouseId], [Quantity], [ExpirationDate])
  VALUES ('cccccccc-0000-0000-0000-000000000003', @ing_flour, @wh_backup, 55.00, NULL);

-- Ordering
IF NOT EXISTS (SELECT 1 FROM [Tanya_Ordering].[Orders] WHERE [OrderId] = @order_1)
  INSERT INTO [Tanya_Ordering].[Orders] ([OrderId], [Status], [CreatedAt], [TotalCost], [Notes])
  VALUES (@order_1, N'Confirmed', SYSUTCDATETIME(), 42.50, N'Seed order (confirmed).');

IF NOT EXISTS (SELECT 1 FROM [Tanya_Ordering].[Orders] WHERE [OrderId] = @order_2)
  INSERT INTO [Tanya_Ordering].[Orders] ([OrderId], [Status], [CreatedAt], [TotalCost], [Notes])
  VALUES (@order_2, N'Draft', DATEADD(MINUTE, -30, SYSUTCDATETIME()), 18.00, N'Seed order (draft).');

IF NOT EXISTS (SELECT 1 FROM [Tanya_Ordering].[OrderItems] WHERE [OrderItemId] = @order_item_1)
  INSERT INTO [Tanya_Ordering].[OrderItems] ([OrderItemId], [OrderId], [IngredientId], [Quantity], [UnitPrice])
  VALUES (@order_item_1, @order_1, @ing_salt, 2.00, 4.50);

IF NOT EXISTS (SELECT 1 FROM [Tanya_Ordering].[OrderItems] WHERE [OrderItemId] = @order_item_2)
  INSERT INTO [Tanya_Ordering].[OrderItems] ([OrderItemId], [OrderId], [IngredientId], [Quantity], [UnitPrice])
  VALUES (@order_item_2, @order_1, @ing_flour, 5.00, 6.50);

IF NOT EXISTS (SELECT 1 FROM [Tanya_Ordering].[OrderItems] WHERE [OrderItemId] = @order_item_3)
  INSERT INTO [Tanya_Ordering].[OrderItems] ([OrderItemId], [OrderId], [IngredientId], [Quantity], [UnitPrice])
  VALUES (@order_item_3, @order_2, @ing_milk, 18.00, 1.00);

IF NOT EXISTS (SELECT 1 FROM [Tanya_Ordering].[StockReservations] WHERE [ReservationId] = @res_1)
  INSERT INTO [Tanya_Ordering].[StockReservations] ([ReservationId], [OrderId], [IngredientId], [ReservedQty], [Status])
  VALUES (@res_1, @order_1, @ing_salt, 2.00, N'Active');

IF NOT EXISTS (SELECT 1 FROM [Tanya_Ordering].[StockReservations] WHERE [ReservationId] = @res_2)
  INSERT INTO [Tanya_Ordering].[StockReservations] ([ReservationId], [OrderId], [IngredientId], [ReservedQty], [Status])
  VALUES (@res_2, @order_1, @ing_flour, 5.00, N'Active');

-- Feedback
IF NOT EXISTS (SELECT 1 FROM [Tanya_Feedback].[FeedbackEntries] WHERE [FeedbackId] = @fb_1)
  INSERT INTO [Tanya_Feedback].[FeedbackEntries] ([FeedbackId], [IngredientId], [Source], [Rating], [Comment], [IsArchived], [CreatedAt])
  VALUES (@fb_1, @ing_salt, N'user', 5, N'Good quality.', 0, DATEADD(DAY, -10, SYSUTCDATETIME()));

IF NOT EXISTS (SELECT 1 FROM [Tanya_Feedback].[FeedbackEntries] WHERE [FeedbackId] = @fb_2)
  INSERT INTO [Tanya_Feedback].[FeedbackEntries] ([FeedbackId], [IngredientId], [Source], [Rating], [Comment], [IsArchived], [CreatedAt])
  VALUES (@fb_2, @ing_salt, N'user', 4, N'Fine crystals.', 0, DATEADD(DAY, -2, SYSUTCDATETIME()));

IF NOT EXISTS (SELECT 1 FROM [Tanya_Feedback].[FeedbackEntries] WHERE [FeedbackId] = @fb_3)
  INSERT INTO [Tanya_Feedback].[FeedbackEntries] ([FeedbackId], [IngredientId], [Source], [Rating], [Comment], [IsArchived], [CreatedAt])
  VALUES (@fb_3, @ing_milk, N'system', 3, N'StockLow event: check freshness.', 0, DATEADD(DAY, -1, SYSUTCDATETIME()));

IF NOT EXISTS (SELECT 1 FROM [Tanya_Feedback].[FeedbackSummary] WHERE [SummaryId] = @sum_salt)
  INSERT INTO [Tanya_Feedback].[FeedbackSummary] ([SummaryId], [IngredientId], [AvgRating], [TotalCount], [LastUpdated])
  VALUES (@sum_salt, @ing_salt, 4.50, 2, SYSUTCDATETIME());

IF NOT EXISTS (SELECT 1 FROM [Tanya_Feedback].[FeedbackSummary] WHERE [SummaryId] = @sum_milk)
  INSERT INTO [Tanya_Feedback].[FeedbackSummary] ([SummaryId], [IngredientId], [AvgRating], [TotalCount], [LastUpdated])
  VALUES (@sum_milk, @ing_milk, 3.00, 1, SYSUTCDATETIME());

