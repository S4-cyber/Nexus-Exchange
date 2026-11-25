"""Native black/green/purple cockpit theme and non-modal control help.

Pure presentation. No command invocation, runtime state changes, network access,
external images or new dependencies. All chrome is packed before the existing
content; nothing floats on top of functional widgets.
"""
import random

BLACK="#030405"
PANEL="#090d0c"
PANEL_ALT="#101713"
GREEN="#39ff70"
TEXT="#b6ffc6"
MUTED="#80b68d"
PURPLE="#a66bff"
PURPLE_DARK="#28183e"
EDGE="#1b6537"
DISABLED="#68806e"
FONT=("Segoe UI",10)
IDLE_HELP="Hover over a control, or press Tab to focus it, for a simple explanation."
HELPS={
    "previous":"Show the previous page of tasks.",
    "next":"Show the next page of tasks.",
    "run offline demonstration":"Run a built-in example using fake data. No outside services are contacted.",
    "import compiled json":"Choose a saved JSON file to review opportunities on your computer.",
    "emergency halt":"Stop new work and ask running work to stop safely. The app stays halted until you resume.",
    "resume offline":"Allow local research again after a halt, if recovery is complete. This never enables payments or bids.",
    "opportunity archive":"Browse opportunities stored on this computer.",
    "evaluate deal scenario json":"Open a saved plan and estimate its hypothetical costs and returns.",
    "export report json":"Save the displayed report to a local JSON file.",
    "scout revenue pathways":"Explore zero-budget and funded research routes and their requirements.",
    "scout lead history":"Browse previously collected leads. Old listings may no longer be active.",
    "ranked matrix":"Compare saved leads by modeled feasibility. Nothing is approved for execution.",
    "owner profile":"Declare your available time, budget, sources and skills for planning.",
    "run procurement fixture":"Test the Scout worker with a built-in example. No live website is opened.",
    "run digital services fixture":"Test the digital-services worker with fake data, not paid work.",
    "recover interrupted council attempts":"Reconcile interrupted review records while halted; this does not resume work.",
    "open selected official notice":"Open the official notice for the selected lead in your browser.",
    "open official notice":"Open the selected official listing in your browser.",
    "filter sources":"Narrow the displayed source catalog using your filters.",
    "open official source":"Open the selected official source in your browser.",
    "open integration documentation":"Open the source's official integration reference.",
    "commercial routes":"Review possible commercial models and their restrictions.",
    "search eu ted (keyless)":"Request a bounded search of public European tenders.",
    "search uk fts":"Request a bounded search of public UK Find a Tender notices.",
    "search canadabuys":"Request a read-only search of Canada's public tender dataset.",
    "research usaspending":"Look up historical government awards. These are not open jobs.",
    "reference fx to usd (keyless)":"Look up an indicative currency rate; this does not exchange money.",
    "atlas sec company lookup":"Request public company filing metadata from the SEC.",
    "search uk contracts finder":"Request a bounded read-only search of UK contract notices.",
    "search sam (read only)":"Request a public SAM.gov opportunity search after you approve it.",
    "refresh checklist":"Rebuild the review checklist from your current choices.",
    "global trade catalog":"Browse sources for finding commercial opportunities.",
    "save local profile":"Save your declared planning preferences on this computer.",
    "reload":"Reload the saved local information.",
    "clear profile":"Remove the saved profile after the app's confirmation.",
    "fingerprint evidence file":"Choose a file and record its digital fingerprint, not its contents.",
    "check saved fingerprint":"Compare a selected file with the saved fingerprint.",
    "save selected task":"Save your local note about the selected checklist item.",
    "filter / refresh":"Apply your filters and reload the local results.",
    "review to do":"Open the evidence checklist for the selected opportunity.",
    "plan scenario":"Open the financial and scheduling assumptions for this opportunity.",
    "export history json":"Save the displayed historical lead report to a JSON file.",
    "search / refresh":"Search and reload saved local records.",
    "export displayed json":"Save the currently displayed records as a JSON file.",
    "inspect saved plan":"Read the saved plan and its current local review checks.",
    "register review task":"Register this plan for local Council review.",
    "run one review attempt":"Run one review attempt. Each attempt counts toward the review limit.",
    "refresh historical audit":"Reload recorded Council attempts and evidence history.",
    "overview":"Show the overview of the selected review context.",
    "summary":"Show the short summary of the selected review context.",
    "detail":"Show the more detailed review context.",
    "review":"Show the local review conclusions and their limits.",
    "evidence":"Show the supporting evidence references without claiming independent verification.",
    "full":"Show the full local review context.",
    "select file":"Choose a file from your computer; nothing is uploaded.",
    "produce and preview":"Create a local CSV sample in memory and check its exact contents.",
    "export new csv":"Save the reviewed CSV to a new file. Existing files are not replaced.",
    "register matching csv":"Record a selected CSV only if it matches the reviewed work sample.",
    "obligation history":"Browse recorded deliverables and local evidence notes.",
    "attach selected local file":"Associate the selected assumption with a local file fingerprint.",
    "reselect file / compare bytes":"Check whether a selected file still matches its saved reference.",
    "refresh coverage":"Reload the list of assumptions and evidence references.",
    "refresh ledger":"Reload the saved simulated invoice and synthetic payment history.",
    "preview simulation":"Preview hypothetical invoice terms; no real invoice is issued.",
    "save simulation":"Save the reviewed hypothetical invoice locally.",
    "record synthetic receipt":"Record a made-up payment for testing. Do not enter a real payment reference.",
    "evaluate as-of date":"Calculate simulated outstanding and overdue balances for the chosen date.",
    "model cash flow and reserve":"Estimate modeled net proceeds and a hypothetical reserve. No money moves.",
    "refresh history":"Reload recorded local obligations.",
    "inspect selected":"Read the selected obligation and its evidence history.",
    "record evidence note":"Record a file fingerprint and your declared note. This does not verify buyer acceptance.",
    "simulated finance":"Open the hypothetical invoice and payment workspace for this obligation.",
    "preview draft":"Preview a local quotation request without sending it.",
    "save immutable draft":"Save the reviewed draft as a local historical record.",
    "refresh saved drafts":"Reload the local quotation draft history.",
    "acknowledge selected locally":"Record your local acknowledgment of the selected draft. Nothing is sent.",
    "prioritize operator hints":"Within each review tier, put leads with matching implemented-service hints first.",
    "refresh ranking":"Recalculate the local ranking using the current filters.",
    "open selected lead planning":"Open the exact selected lead's planning workspace.",
    "review selected to do":"Open the checklist for the selected lead.",
    "new / clear form":"Clear the current inputs to start a new plan.",
    "save immutable plan":"Save these assumptions as a new fixed planning record.",
    "load selected":"Load the selected saved plan into the form.",
    "reassess selected saved plan":"Recalculate the selected plan using current local checks.",
    "assumption evidence":"Open the saved plan's local evidence references.",
    "refresh list":"Reload the saved plans.",
    "council review":"Open Council's local review workspace for this saved plan.",
    "operator rfq":"Open a local request-for-quotation draft workspace.",
    "operator csv work sample":"Open the tool for producing and checking a local CSV sample.",
    "operator json-to-csv work sample":"Convert a selected flat JSON array of string records to a checked CSV without sending it.",
    "operator csv quality report":"Calculate per-column aggregate completeness, distinctness and length statistics locally.",
    "operator csv reconciliation":"Compare two local CSV files by exact unique key; identify missing or changed records without editing source files.",
    "select right file":"Choose the second local CSV to compare against the left file.",
    "capability search planner":"Plan public searches for one implemented service using your saved source choices.",
    "refresh discovery plan":"Rebuild the local search options using the current profile and time.",
    "search selected plan":"Confirm and run only the selected bounded public research search; no bid or payment.",
    "search history":"Review archived completed capability searches and their request and observation counts.",
    "review declared requirements":"Check declared service requirements against the selected current Scout record.",
    "preview exact local sample":"Recheck the reviewed local files and produce a sample without publishing it.",
    "export exact sample":"Reproduce the reviewed sample and create a new local CSV without overwriting a file.",
    "register exact sample":"Recheck a selected matching CSV and record its Scout review in local obligation history; nothing is sent.",
    "animate stars":"Turn the decorative star movement on or off in all app windows. Work continues unchanged.",
}


def help_for(label,widget_class):
    """Plain-language presentation text only; never invoke a widget command."""
    if type(label) is not str:
        label=""
    cleaned=" ".join(label.split())[:120]
    key=cleaned.casefold()
    if key in HELPS:
        return HELPS[key]
    if widget_class in ("Checkbutton","TCheckbutton","Radiobutton","TRadiobutton"):
        return "Choose or clear this option: "+cleaned[:74]+". This is a local setting, not external authorization."
    if widget_class in ("Button","TButton","TMenubutton","Menubutton"):
        return "Use this control for "+(cleaned[:74] or "the labeled local action")+". Review any confirmation before proceeding."
    if widget_class=="TCombobox":
        return "Choose an option from the list."
    if widget_class in ("Entry","TEntry","Spinbox","TSpinbox"):
        return "Enter or edit the value for the nearby label."
    if widget_class in ("Treeview","Listbox"):
        return "Select a row to inspect it or use the available local actions."
    if widget_class in ("Text",):
        return "Read the details shown here, or enter text if this field is editable."
    return None


def drift(x,y,dx,dy):
    """Loop normalized star positions; no dependence on viewport size."""
    return (x+dx)%1.0,(y+dy)%1.0


def fit_geometry(window,width,height):
    # Give existing content room for the dock/rails where the display permits.
    w=min(width+34,max(320,window.winfo_screenwidth()-44))
    h=min(height+88,max(320,window.winfo_screenheight()-100))
    return f"{w}x{h}"


def configure_theme(window):
    import tkinter as tk
    from tkinter import ttk

    root=window.nametowidget(".")
    if getattr(root,"_nexus_cockpit_theme",False):
        window.configure(background=BLACK)
        return root
    root._nexus_cockpit_theme=True
    root.configure(background=BLACK)
    window.configure(background=BLACK)
    style=ttk.Style(root)
    style.theme_use("clam")
    style.configure(".",font=FONT,background=BLACK,foreground=TEXT,
                    fieldbackground=PANEL,bordercolor=EDGE,lightcolor=EDGE,darkcolor=BLACK)
    style.configure("TFrame",background=BLACK)
    style.configure("TLabel",background=BLACK,foreground=TEXT)
    style.configure("TLabelframe",background=BLACK,bordercolor=GREEN,relief="solid",borderwidth=1,
                    lightcolor=EDGE,darkcolor=EDGE)
    style.configure("TLabelframe.Label",background=BLACK,foreground=GREEN,font=("Segoe UI",10,"bold"))
    style.configure("TButton",background=PANEL_ALT,foreground=GREEN,bordercolor=EDGE,
                    lightcolor=EDGE,darkcolor=EDGE,focuscolor=PURPLE,padding=(5,4))
    style.map("TButton",background=[("disabled",PANEL),("pressed",PURPLE_DARK),("active","#192a20")],
              foreground=[("disabled",DISABLED),("active","#d2ffe0")],
              bordercolor=[("disabled","#20332a"),("focus",PURPLE),("active",GREEN)])
    style.configure("Halt.TButton",background=PURPLE_DARK,foreground=GREEN,bordercolor=PURPLE,
                    lightcolor=PURPLE,darkcolor=EDGE,font=("Segoe UI",10,"bold"))
    style.map("Halt.TButton",background=[("pressed","#432360"),("active","#3a2456")],
              foreground=[("active","#dcffe4")],bordercolor=[("focus",GREEN),("active",PURPLE)])
    for item in ("TCheckbutton","TRadiobutton"):
        style.configure(item,background=BLACK,foreground=TEXT,indicatorcolor=PANEL,focuscolor=PURPLE)
        style.map(item,foreground=[("disabled",DISABLED),("active",GREEN)],
                  background=[("active",PANEL)],indicatorcolor=[("selected",PURPLE),("active",EDGE)])
    for item in ("TEntry","TCombobox","TSpinbox"):
        style.configure(item,foreground=GREEN,fieldbackground=PANEL,background=PANEL_ALT,
                        bordercolor=EDGE,lightcolor=EDGE,darkcolor=BLACK,insertcolor=GREEN,arrowcolor=GREEN)
        style.map(item,fieldbackground=[("disabled",PANEL),("readonly",PANEL_ALT)],
                  foreground=[("disabled",DISABLED),("readonly",GREEN)],
                  bordercolor=[("focus",PURPLE)])
    style.configure("Treeview",foreground=TEXT,background=PANEL,fieldbackground=PANEL,
                    bordercolor=GREEN,rowheight=23)
    style.map("Treeview",background=[("selected",PURPLE_DARK)],foreground=[("selected","#e0ffe5")])
    style.configure("Treeview.Heading",background=PANEL_ALT,foreground=GREEN,bordercolor=EDGE,
                    font=("Segoe UI",10,"bold"))
    style.map("Treeview.Heading",background=[("active",PURPLE_DARK)])
    style.configure("TNotebook",background=BLACK,bordercolor=EDGE)
    style.configure("TNotebook.Tab",background=PANEL,foreground=GREEN,padding=(8,4))
    style.map("TNotebook.Tab",background=[("selected",PURPLE_DARK),("active",PANEL_ALT)],
              foreground=[("selected","#e0ffe5")])
    for item in ("Vertical.TScrollbar","Horizontal.TScrollbar"):
        style.configure(item,background=EDGE,troughcolor=PANEL,bordercolor=BLACK,arrowcolor=GREEN)
        style.map(item,background=[("active",PURPLE),("pressed",PURPLE_DARK)])
    for kind in ("Text","Entry","Listbox"):
        for option,value in (("background",PANEL),("foreground",TEXT),
                             ("selectBackground",PURPLE_DARK),("selectForeground","#e0ffe5"),
                             ("highlightBackground",EDGE),("highlightColor",PURPLE),
                             ("highlightThickness",1)):
            root.option_add("*"+kind+"."+option,value)
    root.option_add("*Text.insertBackground",GREEN)
    root.option_add("*Entry.insertBackground",GREEN)
    root.option_add("*TCombobox*Listbox.background",PANEL)
    root.option_add("*TCombobox*Listbox.foreground",TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground",PURPLE_DARK)
    root.option_add("*TCombobox*Listbox.selectForeground","#e0ffe5")
    root._nexus_star_motion=tk.BooleanVar(master=root,value=True)
    return root


class StarRail:
    """Small exposed viewport with moving stars and fixed angular illuminated trim."""
    def __init__(self,window,orientation,count,seed):
        import tkinter as tk
        self.orientation=orientation
        self.canvas=tk.Canvas(window,background=BLACK,highlightthickness=0,borderwidth=0,
                              width=16 if orientation!="top" else 1,
                              height=30 if orientation=="top" else 1,takefocus=False)
        self.stars=[]
        rng=random.Random(seed)
        for i in range(count):
            x,y=rng.random(),rng.random()
            radius=rng.choice((0.65,0.85,1.0,1.3,1.65))
            dx=-(0.0005+rng.random()*0.0014) if orientation=="top" else 0.0012+rng.random()*0.002
            dy=(0.0009+rng.random()*0.002) if orientation=="top" else 0.0006+rng.random()*0.002
            item=self.canvas.create_oval(0,0,1,1,outline="",
                fill=rng.choice(("#d4e5e1","#8eeac1","#8e6bbf","#589a74")),tags=("star",))
            self.stars.append([item,x,y,dx,dy,radius])
        self.canvas.bind("<Configure>",self.resize,add="+")
        self.resize()

    def resize(self,_event=None):
        c=self.canvas
        w,h=max(1,c.winfo_width()),max(1,c.winfo_height())
        c.delete("trim")
        if self.orientation=="top":
            corner=min(110,w*.23)
            for y,color,width in ((h-2,EDGE,4),(h-3,GREEN,1)):
                c.create_line(0,0,corner,y,w-corner,y,w,0,fill=color,width=width,tags="trim")
            c.create_line(corner+10,h-8,w-corner-10,h-8,fill=PURPLE,width=1,tags="trim")
        else:
            inside=w-2 if self.orientation=="left" else 2
            outside=2 if self.orientation=="left" else w-2
            bend=min(42,h*.12)
            c.create_line(outside,0,inside,bend,inside,h-bend,outside,h,
                          fill=EDGE,width=4,tags="trim")
            c.create_line(outside,0,inside,bend,inside,h-bend,outside,h,
                          fill=GREEN,width=1,tags="trim")
            c.create_line(outside,bend,outside,h-bend,fill=PURPLE,width=1,tags="trim")
        self.paint()
        c.tag_raise("trim")

    def paint(self):
        w,h=max(1,self.canvas.winfo_width()),max(1,self.canvas.winfo_height())
        for item,x,y,_dx,_dy,r in self.stars:
            self.canvas.coords(item,x*w-r,y*h-r,x*w+r,y*h+r)

    def advance(self):
        for star in self.stars:
            star[1],star[2]=drift(star[1],star[2],star[3],star[4])
        self.paint()


def reveal_fraction(start,size,offset,visible,total):
    """Keep a focused control in view; None means no movement is needed."""
    if total<=visible or visible<=0 or size<=0:
        return None
    if start>=offset and start+size<=offset+visible:
        return None
    target=start if start<offset or size>=visible else start+size-visible
    target=max(0,min(target,total-visible))
    if abs(target-offset)<1:
        return None
    return target/total


class WorkspaceViewport:
    """A reserved two-axis content viewport; never overlays fixed controls."""
    def __init__(self,window):
        import tkinter as tk
        from tkinter import ttk
        self.frame=ttk.Frame(window)
        self.frame.pack(fill="both",expand=True)
        self.frame.rowconfigure(0,weight=1)
        self.frame.columnconfigure(0,weight=1)
        self.canvas=tk.Canvas(self.frame,background=BLACK,highlightthickness=0,
                              borderwidth=0,width=1,height=1,takefocus=False)
        self.canvas.grid(row=0,column=0,sticky="nsew")
        ybar=ttk.Scrollbar(self.frame,orient="vertical",command=self.canvas.yview)
        xbar=ttk.Scrollbar(self.frame,orient="horizontal",command=self.canvas.xview)
        ybar.grid(row=0,column=1,sticky="ns")
        xbar.grid(row=1,column=0,sticky="ew")
        self.canvas.configure(yscrollcommand=ybar.set,xscrollcommand=xbar.set)
        self.content=ttk.Frame(self.canvas)
        self.item=self.canvas.create_window(0,0,anchor="nw",window=self.content)
        self.extent=(0,0)
        self.pending=None
        self.closed=False
        self.canvas.bind("<Configure>",self.queue,add="+")
        self.content.bind("<Configure>",self.queue,add="+")
        self.frame.bind("<Destroy>",self.destroy,add="+")
        self.queue()

    def queue(self,_event=None):
        if not self.closed and self.pending is None:
            self.pending=self.frame.after_idle(self.flush)

    def flush(self):
        self.pending=None
        self.sync()

    def sync(self):
        if self.closed:
            return
        width=max(1,self.canvas.winfo_width(),self.content.winfo_reqwidth())
        height=max(1,self.canvas.winfo_height(),self.content.winfo_reqheight())
        if (width,height)!=self.extent:
            self.extent=(width,height)
            self.canvas.itemconfigure(self.item,width=width,height=height)
            self.canvas.configure(scrollregion=(0,0,width,height))

    def contains(self,widget):
        return widget is not None and str(widget).startswith(str(self.content)+".")

    def reveal(self,widget):
        if self.closed or not self.contains(widget) or not widget.winfo_ismapped():
            return
        self.sync()
        for axis,start,size,offset,visible,total in (
            ("x",widget.winfo_rootx()-self.content.winfo_rootx(),widget.winfo_width(),
             self.canvas.canvasx(0),self.canvas.winfo_width(),self.extent[0]),
            ("y",widget.winfo_rooty()-self.content.winfo_rooty(),widget.winfo_height(),
             self.canvas.canvasy(0),self.canvas.winfo_height(),self.extent[1])):
            fraction=reveal_fraction(start,size,offset,visible,total)
            if fraction is not None:
                if axis=="x":
                    self.canvas.xview_moveto(fraction)
                else:
                    self.canvas.yview_moveto(fraction)

    def destroy(self,event):
        if event.widget==self.frame:
            self.closed=True
            if self.pending is not None:
                self.frame.after_cancel(self.pending)
                self.pending=None


class Cockpit:
    def __init__(self,window,*,command_deck=False):
        import tkinter as tk
        from tkinter import ttk
        self.window=window
        self.root=configure_theme(window)
        self.motion=self.root._nexus_star_motion
        self.active=None
        self.timer=None
        self.closed=False
        self.help=tk.StringVar(master=window,value=IDLE_HELP)
        # Pack these before the original interface; footer is reserved, not an overlay.
        self.footer=tk.Frame(window,background=BLACK,height=64,
                            highlightbackground=EDGE,highlightthickness=1)
        self.footer.pack(side="bottom",fill="x",padx=5,pady=(3,5))
        self.footer.pack_propagate(False)
        controls=ttk.Frame(self.footer)
        controls.pack(side="left",fill="y",padx=10,pady=3)
        ttk.Label(controls,text="NEXUS // COCKPIT",foreground=GREEN,
                  font=("Segoe UI",10,"bold")).pack(anchor="w")
        ttk.Checkbutton(controls,text="Animate stars",variable=self.motion).pack(anchor="w")
        self.help_box=tk.Frame(self.footer,background=PANEL,highlightbackground=PURPLE,
                              highlightthickness=1)
        self.help_box.pack(side="right",fill="both",expand=True,padx=8,pady=4)
        self.help_label=tk.Label(self.help_box,textvariable=self.help,background=PANEL,foreground=TEXT,
                                justify="left",anchor="nw",font=FONT,padx=8,pady=4,
                                wraplength=420)
        self.help_label.pack(fill="both",expand=True)
        self.help_label.bind("<Configure>",self._wrap,add="+")
        self.rails=[StarRail(window,"top",42,11),StarRail(window,"left",18,23),StarRail(window,"right",18,37)]
        self.rails[0].canvas.pack(side="top",fill="x")
        self.rails[1].canvas.pack(side="left",fill="y")
        self.rails[2].canvas.pack(side="right",fill="y")
        # The dashboard's safety deck is outside scrolling content.
        self.safety=ttk.Frame(window) if command_deck else None
        if self.safety is not None:
            self.safety.pack(side="top",fill="x",padx=6,pady=(3,4))
        self.viewport=WorkspaceViewport(window)
        self.content=self.viewport.content
        # Every descendant's default bindtags include its own toplevel.
        # No global bind_all and no button command/state changes.
        window.bind("<Enter>",self._enter,add="+")
        window.bind("<Leave>",self._leave,add="+")
        window.bind("<FocusIn>",self._focus,add="+")
        window.bind("<FocusOut>",self._leave,add="+")
        window.bind("<Destroy>",self._destroy,add="+")
        self.timer=window.after(65,self._tick)

    def _wrap(self,event):
        width=max(80,event.width-18)
        if int(self.help_label.cget("wraplength"))!=width:
            self.help_label.configure(wraplength=width)

    def _enter(self,event):
        self.show(getattr(event,"widget",None))

    def _focus(self,event):
        widget=getattr(event,"widget",None)
        self.show(widget)
        self.viewport.reveal(widget)

    def show(self,widget):
        try:
            if widget is None or widget.winfo_toplevel()!=self.window:
                return
            kind=widget.winfo_class()
            label=widget.cget("text") if kind in (
                "TButton","Button","TCheckbutton","Checkbutton","TRadiobutton","Radiobutton",
                "TMenubutton","Menubutton") else ""
            message=help_for(label,kind)
        except (AttributeError,TypeError):
            return
        if message is not None:
            self.active=widget
            self.help.set(message)

    def _leave(self,event):
        if getattr(event,"widget",None)==self.active:
            self.active=None
            self.help.set(IDLE_HELP)

    def _tick(self):
        self.timer=None
        if self.closed:
            return
        if self.motion.get() and self.window.winfo_viewable():
            for rail in self.rails:
                rail.advance()
            delay=65
        else:
            delay=250
        self.timer=self.window.after(delay,self._tick)

    def _destroy(self,event):
        if event.widget==self.window:
            self.closed=True
            if self.timer is not None:
                self.window.after_cancel(self.timer)
                self.timer=None


def install_cockpit(window,*,command_deck=False):
    if not hasattr(window,"_nexus_cockpit"):
        window._nexus_cockpit=Cockpit(window,command_deck=command_deck)
    return window._nexus_cockpit


def smoke_cockpit(root,halt_button):
    """Exercise real native widgets in existing Windows source/frozen GUI smoke."""
    import tkinter as tk
    from tkinter import ttk
    chrome=install_cockpit(root)
    if chrome.safety is None or halt_button.master.master!=chrome.safety or chrome.viewport.contains(halt_button):
        raise RuntimeError("emergency halt must remain outside the scrolling dashboard")
    original=str(halt_button.cget("state"))
    chrome.show(halt_button)
    if chrome.help.get()!=HELPS["emergency halt"] or str(halt_button.cget("state"))!=original:
        raise RuntimeError("cockpit emergency help changed control state")
    if ttk.Style(root).lookup("TButton","foreground")!=GREEN:
        raise RuntimeError("cockpit global green theme missing")
    child=tk.Toplevel(root)
    child.geometry("520x300")
    try:
        sub=install_cockpit(child)
        spacer=ttk.Frame(sub.content,width=900,height=500)
        spacer.pack()
        button=ttk.Button(sub.content,text="Export new CSV",command=lambda:None)
        button.pack()
        child.update_idletasks()
        sub.viewport.sync()
        child.update_idletasks()
        if sub.viewport.extent[0]<900 or sub.viewport.extent[1]<500:
            raise RuntimeError("cockpit content extent clipped")
        if sub.viewport.canvas.winfo_width()>=sub.viewport.extent[0] or sub.viewport.canvas.winfo_height()>=sub.viewport.extent[1]:
            raise RuntimeError("small viewport smoke did not create scroll overflow")
        sub.viewport.canvas.xview_moveto(1)
        sub.viewport.canvas.yview_moveto(1)
        if sub.viewport.canvas.xview()[0]<=0 or sub.viewport.canvas.yview()[0]<=0:
            raise RuntimeError("cockpit overflow not reachable")
        if sub.viewport.contains(sub.footer):
            raise RuntimeError("help dock must not scroll")
        if sub.motion is not chrome.motion or sub.footer not in child.pack_slaves():
            raise RuntimeError("cockpit child or reserved help dock missing")
        sub.show(button)
        if sub.help.get()!=HELPS["export new csv"]:
            raise RuntimeError("cockpit child help missing")
        if child.winfo_viewable():
            button.event_generate("<Enter>",when="now")
            if sub.help.get()!=HELPS["export new csv"]:
                raise RuntimeError("cockpit hover binding failed")
        before=tuple(sub.rails[0].stars[0][1:3])
        sub.rails[0].advance()
        if tuple(sub.rails[0].stars[0][1:3])==before:
            raise RuntimeError("cockpit star animation stalled")
        chrome.motion.set(False)
        if sub.motion.get():
            raise RuntimeError("cockpit motion switch not shared")
        chrome.motion.set(True)
    finally:
        child.destroy()
    if not sub.closed or sub.timer is not None or not sub.viewport.closed or sub.viewport.pending is not None:
        raise RuntimeError("cockpit timer not cleaned up")
    chrome.active=None
    chrome.help.set(IDLE_HELP)
