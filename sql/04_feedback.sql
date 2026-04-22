-- Tanya_Feedback tables
IF OBJECT_ID(N'[Tanya_Feedback].[FeedbackEntries]', N'U') IS NULL
BEGIN
  CREATE TABLE [Tanya_Feedback].[FeedbackEntries] (
    [FeedbackId] UNIQUEIDENTIFIER NOT NULL CONSTRAINT [PK_TanyaFeedback_FeedbackEntries] PRIMARY KEY,
    [IngredientId] UNIQUEIDENTIFIER NOT NULL,
    [Source] NVARCHAR(50) NOT NULL,
    [Rating] TINYINT NOT NULL,
    [Comment] NVARCHAR(MAX) NULL,
    [IsArchived] BIT NOT NULL CONSTRAINT [DF_TanyaFeedback_FeedbackEntries_IsArchived] DEFAULT (0),
    [CreatedAt] DATETIME2 NOT NULL
  );

  ALTER TABLE [Tanya_Feedback].[FeedbackEntries]
    ADD CONSTRAINT [CK_TanyaFeedback_FeedbackEntries_RatingRange] CHECK ([Rating] >= 1 AND [Rating] <= 5);
END

IF OBJECT_ID(N'[Tanya_Feedback].[FeedbackSummary]', N'U') IS NULL
BEGIN
  CREATE TABLE [Tanya_Feedback].[FeedbackSummary] (
    [SummaryId] UNIQUEIDENTIFIER NOT NULL CONSTRAINT [PK_TanyaFeedback_FeedbackSummary] PRIMARY KEY,
    [IngredientId] UNIQUEIDENTIFIER NOT NULL,
    [AvgRating] DECIMAL(3,2) NOT NULL,
    [TotalCount] INT NOT NULL,
    [LastUpdated] DATETIME2 NOT NULL
  );

  ALTER TABLE [Tanya_Feedback].[FeedbackSummary]
    ADD CONSTRAINT [UQ_TanyaFeedback_FeedbackSummary_IngredientId] UNIQUE ([IngredientId]);
END

