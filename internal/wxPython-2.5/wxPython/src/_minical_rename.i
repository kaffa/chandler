// A bunch of %rename directives generated by BuildRenamers in config.py
// in order to remove the wx prefix from all global scope names.

#ifndef BUILDING_RENAMERS

%rename(CAL_SUNDAY_FIRST)                   wxCAL_SUNDAY_FIRST;
%rename(CAL_MONDAY_FIRST)                   wxCAL_MONDAY_FIRST;
%rename(CAL_SHOW_SURROUNDING_WEEKS)         wxCAL_SHOW_SURROUNDING_WEEKS;
%rename(CAL_SHOW_PREVIEW)                   wxCAL_SHOW_PREVIEW;
%rename(CAL_HITTEST_NOWHERE)                wxCAL_HITTEST_NOWHERE;
%rename(CAL_HITTEST_HEADER)                 wxCAL_HITTEST_HEADER;
%rename(CAL_HITTEST_DAY)                    wxCAL_HITTEST_DAY;
%rename(CAL_HITTEST_TODAY)                  wxCAL_HITTEST_TODAY;
%rename(CAL_HITTEST_INCMONTH)               wxCAL_HITTEST_INCMONTH;
%rename(CAL_HITTEST_DECMONTH)               wxCAL_HITTEST_DECMONTH;
%rename(CAL_HITTEST_SURROUNDING_WEEK)       wxCAL_HITTEST_SURROUNDING_WEEK;
%rename(MiniCalendarDateAttr)               wxMiniCalendarDateAttr;
%rename(MiniCalendarEvent)                  wxMiniCalendarEvent;
%rename(MiniCalendar)                       wxMiniCalendar;

#endif
