import argparse
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Generate Rocoto XML from template.")
    parser.add_argument("--pslot", default="obsmon_test")
    parser.add_argument("--start_date")
    args = parser.parse_args()

    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("monitor_rocoto_template.xml.j2")

    output = template.render(
        PSLOT=args.pslot,
        HOMEobsmon="/scratch1/NCEPDEV/da/Kevin.Dougherty/obs-monitor",
        COMROOT="/scratch1/NCEPDEV/da/Kevin.Dougherty/com",
        DATAROOT="/scratch1/NCEPDEV/da/Kevin.Dougherty/test",
        CONFIG_YAML="/scratch1/NCEPDEV/da/Kevin.Dougherty/obs-monitor/config/obs_monitor_config.yaml",
        RUNTIMEDIR="/scratch1/NCEPDEV/da/Kevin.Dougherty/obs-monitor/driver/",
        NCYCLES="1",
        INTERVAL_HOURS="6",
        OUTDIR="/scratch1/NCEPDEV/da/Kevin.Dougherty/outdir",
        SCHEDULER="slurm",
        SDATE=args.start_date,
        ACCOUNT="da-cpu",
        QUEUE="batch",
        PARTITION="standard",
        WALLTIME="00:15:00",
        TASK_NODES="1",
        TASK_MEM="4G"
    )

    Path('obsmon_workflow.xml').parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        f.write(output)
    print(f"Rocoto workflow written to {args.output}")

if __name__ == "__main__":
    main()