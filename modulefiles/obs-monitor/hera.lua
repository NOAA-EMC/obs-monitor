help([[
Load python virtual environment for obs-monitor
]])

local pkgName    = myModuleName()
local pkgVersion = myModuleVersion()
local pkgNameVer = myModuleFullName()

conflict(pkgName)


prepend_path("MODULEPATH", "/scratch1/NCEPDEV/nems/role.epic/spack-stack/spack-stack-1.6.0/envs/unified-env-rocky8/install/modulefiles/Core")

load ("stack-intel/2021.5.0")
load ("python/3.10.13")

local pyenvpath = "/scratch1/NCEPDEV/da/Edward.Safford/noscrub/python/envs/"
local pyenvname = "obs-mon"

local pyenvactivate = pathJoin(pyenvpath, pyenvname, "bin/activate")

if (mode() == "load") then
  local activate_cmd = "source "..pyenvactivate
  execute{cmd=activate_cmd, modeA={"load"}}
  prepend_path("PATH", "/scratch1/NCEPDEV/da/Edward.Safford/noscrub/python/envs/obs-mon/bin")
  prepend_path("PYTHONPATH", "/scratch1/NCEPDEV/da/Edward.Safford/noscrub/python/envs/obs-mon")

else
  if (mode() == "unload") then
    local deactivate_cmd = "deactivate"
    execute{cmd=deactivate_cmd, modeA={"unload"}}
  end
end

whatis("Name: ".. pkgName)
whatis("Version: ".. pkgVersion)
whatis("Category: Obs-monitor")
whatis("Description: Load all libraries needed for obs-monitor")

