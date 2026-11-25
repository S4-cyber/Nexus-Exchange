"""Windows desktop preview; no external operations."""
import sys
from datetime import datetime, timezone, timedelta
from nexus_exchange.pipeline import evaluate_snapshots

def demo():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    stamp = now.isoformat()
    release = dict(ocid="ocds-demo-1", id="demo-1", date=stamp,
        tender=dict(status="active", title="Synthetic procurement opportunity",
        tenderPeriod=dict(endDate=(now+timedelta(days=7)).isoformat()),
        value=dict(amount=1000,currency="USD")))
    return evaluate_snapshots("demo",[release],"https://example.org/demo",stamp,now=now,halted=False)

def main():
    import tkinter as tk
    from tkinter import ttk
    root = tk.Tk()
    root.title("Nexus Exchange | Offline preview")
    root.geometry("840x540")
    ttk.Label(root,text="NEXUS EXCHANGE",font=("Segoe UI",24)).pack(pady=20)
    ttk.Label(root,text="OFFLINE DEMONSTRATION — External actions disabled").pack()
    output = tk.Text(root,height=16,wrap="word")
    output.pack(fill="both",expand=True,padx=20,pady=16)
    output.configure(state="disabled")
    def run():
        output.configure(state="normal")
        output.delete("1.0","end")
        try:
            for item in demo():
                o=item.observation.opportunity
                output.insert("end",f"{o.title}\nValue: {o.currency} {o.amount}\nReview eligible: {item.screening.eligible_for_review}\nReasons: {item.screening.reasons}\nSynthetic data only.\n")
        except Exception as exc:
            output.insert("end",f"Screening failed: {type(exc).__name__}")
        finally:
            output.configure(state="disabled")
    ttk.Button(root,text="Run offline demonstration",command=run).pack(pady=10)
    root.mainloop()

if __name__ == "__main__":
    if "--self-test" in sys.argv:
        import tkinter
        result=demo()
        sys.exit(0 if len(result)==1 and result[0].screening.eligible_for_review else 1)
    main()
