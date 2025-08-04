import argparse
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Generate Rocoto XML from template.")
    parser.add_argument("--pslot", required=True, help="PSLOT name for workflow")
    parser.add_argument("--start_date", required=True, help="Cycle start date in YYYYMMDDHH format")
    parser.add_argument("--end_date", required=True, help="Cycle end date in YYYYMMDDHH format")
    parser.add_argument("--obsmondir", required=True, help="Path to base obs-monitor directory")
    parser.add_argument("--expdir", required=True, help="Experiment directory (EXPDIR)")
    parser.add_argument("--comroot", required=True, help="COMROOT directory")
    parser.add_argument("--dataroot", required=True, help="DATAROOT directory")
    parser.add_argument("--intervalhrs", default="6", help="Hours between cycles")
    parser.add_argument("--copydata", default=False, help="Copy data to /local")
    parser.add_argument("--keepdata", default=False, help="Keep runtime directory, data, and figures")
    args = parser.parse_args()

    env = Environment(loader=FileSystemLoader("."))
    template = env.get_template("monitor_rocoto_template.xml.j2")

    # Assign variables first to avoid reference issues
    pslot = args.pslot
    obsmondir = args.obsmondir
    expdir = args.expdir
    runtime_dir = f"{expdir}/{pslot}"
    config_yaml = f"{obsmondir}/driver/config.yaml"
    output_path = f"{runtime_dir}/{pslot}_obsmon_rocoto.xml"

    output = template.render(
        PSLOT=pslot,
        HOMEobsmon=obsmondir,
        COMROOT=args.comroot,
        EXPDIR=expdir,
        DATAROOT=args.dataroot,
        RUNTIME_DIR=runtime_dir,
        CONFIG_YAML=config_yaml,
        SCHEDULER="slurm",
        SDATE=args.start_date,
        EDATE=args.end_date,
        INTERVAL_HOURS=args.intervalhrs,
        ACCOUNT="da-cpu",
        QUEUE="batch",
        WALLTIME="00:15:00",
        TASK_NODES='1:ppn=1:tpp=1',
        TASK_MEM="4G",
        COPY_DATA=args.copydata,
        KEEP_DATA=args.keepdata
    )
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        f.write(output)
    
    print(f"Rocoto workflow written to {output_path}")

if __name__ == "__main__":
    main()
