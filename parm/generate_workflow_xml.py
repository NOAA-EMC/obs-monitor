from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader("."))
template = env.get_template("monitor_rocoto_template.xml.j2")

output = template.render(
    PSLOT="obsmon_test",
    HOMEobsmon="/scratch1/NCEPDEV/da/Kevin.Dougherty/obs-monitor",
    COMROOT="/scratch1/NCEPDEV/da/Kevin.Dougherty/com",
    DATAROOT="/scratch1/NCEPDEV/da/Kevin.Dougherty/dataroot",
    CONFIG_YAML="/scratch1/NCEPDEV/da/Kevin.Dougherty/obs-monitor/config/obs_monitor_config.yaml",
    SCHEDULER="slurm",
    SDATE="2025062800",
    EDATE="2025070100",
    ACCOUNT="da-cpu",
    QUEUE="batch",
    PARTITION="standard",
    WALLTIME="00:15:00",
    TASK_NODES="1",
    TASK_MEM="4G"
)

with open("monitor_rocoto_template.xml", "w") as f:
    f.write(output)