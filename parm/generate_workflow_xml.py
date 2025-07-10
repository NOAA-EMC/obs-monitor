import argparse
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Generate Rocoto XML from template.")
    parser.add_argument("--pslot", default="obsmon_test")
    parser.add_argument("--start_date", required=True)
    parser.add_argument("--output", required=True, help="Path to output XML file")
    args = parser.parse_args()

    env = Environment(loader=FileSystemLoader("."))
    template = env.get_template("monitor_rocoto_template.xml.j2")

    output = template.render(
        PSLOT=args.pslot,
        HOMEobsmon="/scratch3/NCEPDEV/da/Kevin.Dougherty/obs-monitor",
        COMROOT="/scratch3/NCEPDEV/da/Kevin.Dougherty/obsmon_save",
        EXPDIR="/scratch3/NCEPDEV/da/Kevin.Dougherty/obsmon_exp",
        DATAROOT="/scratch3/NCEPDEV/da/Kevin.Dougherty/test",
        RUNTIME_DIR=f"{EXPDIR}/{PSLOT}",
        CONFIG_YAML=f"{HOMEobsmon}/driver/config2.yaml",
        NCYCLES="1", # number of cycles to work back from start date
        INTERVAL_HOURS="6",
        SCHEDULER="slurm",
        SDATE=args.start_date,
        ACCOUNT="da-cpu",
        QUEUE="batch",
        PARTITION="standard",
        WALLTIME="00:15:00",
        TASK_NODES="1",
        TASK_MEM="4G"
    )

    # need to point this to our EXPDIR, so just make 'output' EXPDIR?
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        f.write(output)
    print(f"Rocoto workflow written to {args.output}")

if __name__ == "__main__":
    main()