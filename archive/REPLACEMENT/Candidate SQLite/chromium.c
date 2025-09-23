// Copyright 2017 The Chromium Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// The database schema is defined here. The constants defined here are used
// by the database manipulation and migration code.

namespace download {
namespace Schema {

// The name of the table that holds the download entries.
constexpr char kDownloadTable[] = "downloads";

// The columns in the downloads table.
constexpr char kId[] = "id";
constexpr char kGuid[] = "guid";
constexpr char kCurrentPath[] = "current_path";
constexpr char kTargetPath[] = "target_path";
// ... (many other columns for URLs, MIME types, etc.)
constexpr char kState[] = "state";
constexpr char kDangerType[] = "danger_type";
constexpr char kInterruptReason[] = "interrupt_reason";
constexpr char kStartTime[] = "start_time";
constexpr char kEndTime[] = "end_time";
// ... (many other columns)

// The query to create the downloads table.
constexpr char kCreateDownloadTableQuery[] =
    "CREATE TABLE downloads("
    "id INTEGER PRIMARY KEY,"
    "guid VARCHAR NOT NULL,"
    "current_path VARCHAR NOT NULL,"
    "target_path VARCHAR NOT NULL,"
    // ... (many other columns)
    "state INTEGER NOT NULL,"
    "danger_type INTEGER NOT NULL,"
    "interrupt_reason INTEGER NOT NULL,"
    "start_time INTEGER NOT NULL,"
    "end_time INTEGER NOT NULL"
    // ... (many other columns)
    ")";

}  // namespace Schema
}  // namespace download


// Copyright 2017 The Chromium Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "sql/statement.h"
// ... other includes

namespace download {
// ...

bool DownloadDatabase::UpdateDownload(const DownloadInfo& info) {
  DCHECK(owning_task_runner_->RunsTasksInCurrentSequence());
  if (!db_)
    return false;

  sql::Statement statement(db_->GetCachedStatement(
      SQL_FROM_HERE,
      "INSERT OR REPLACE INTO downloads "
      "(guid, current_path, target_path, start_time, received_bytes, "
      // ... (many other columns)
      "state, danger_type, interrupt_reason, end_time, total_bytes) "
      "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"));

  // Bind all the parameters from the 'info' object to the SQL statement.
  statement.BindString(0, info.guid);
  statement.BindString(1, info.current_path.value());
  // ... (many other bindings)
  statement.BindInt(10, static_cast<int>(info.state));
  statement.BindInt(11, static_cast<int>(info.danger_type));
  // ... (many other bindings)

  return statement.Run();
}
//...
} // namespace download