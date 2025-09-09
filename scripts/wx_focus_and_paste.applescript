tell application "System Events"
tell process "WeChat"
    set frontmost to true
    delay 0.3
    set w to front window
    try
      set g1 to group 1 of w
    on error
      return "no group 1 on front window"
    end try
    try
      set g2 to group 1 of g1
    on error
      return "no group 1 inside group 1"
    end try
    set report to ""
    set ta to 0
    set tf to 0
    set sa to 0
    set gp to 0
    try
      set ta to (count of text areas of g2)
    end try
    try
      set tf to (count of text fields of g2)
    end try
    try
      set sa to (count of scroll areas of g2)
    end try
    try
      set gp to (count of groups of g2)
    end try
    set report to report & "g1->g1: ta=" & ta & " tf=" & tf & " sa=" & sa & " gp=" & gp & linefeed
    try
      set uiCount to (count of UI elements of g2)
      repeat with i from 1 to uiCount
        set e to UI element i of g2
        set r to ""
        try
          set r to role of e
        end try
        set eta to 0
        set etf to 0
        set esa to 0
        set egp to 0
        try
          set eta to (count of text areas of e)
        end try
        try
          set etf to (count of text fields of e)
        end try
        try
          set esa to (count of scroll areas of e)
        end try
        try
          set egp to (count of groups of e)
        end try
        set report to report & i & ": " & r & " ta=" & eta & " tf=" & etf & " sa=" & esa & " gp=" & egp & linefeed
      end repeat
    end try
    return report
end tell
end tell
OSA