/////////////////////////////////////////////////////////////////////////////
// Name:        wx/msw/dcscreen.h
// Purpose:     wxScreenDC class
// Author:      Julian Smart
// Modified by:
// Created:     01/02/97
// RCS-ID:      $Id: dcscreen.h,v 1.14 2005/12/25 02:34:35 VZ Exp $
// Copyright:   (c) Julian Smart
// Licence:     wxWindows licence
/////////////////////////////////////////////////////////////////////////////

#ifndef _WX_MSW_DCSCREEN_H_
#define _WX_MSW_DCSCREEN_H_

#include "wx/dc.h"

class WXDLLEXPORT wxScreenDC : public wxDC
{
public:
    // Create a DC representing the whole screen
    wxScreenDC();

    // these functions are obsolete and shouldn't be used

    // Compatibility with X's requirements for drawing on top of all windows
    wxDEPRECATED( static bool StartDrawingOnTop(wxWindow* window) );
    wxDEPRECATED( static bool StartDrawingOnTop(wxRect* rect = NULL) );
    wxDEPRECATED( static bool EndDrawingOnTop() );

protected:
    virtual void DoGetSize(int *w, int *h) const
    {
        GetDeviceSize(w, h);
    }

private:
    DECLARE_DYNAMIC_CLASS_NO_COPY(wxScreenDC)
};

#endif // _WX_MSW_DCSCREEN_H_

