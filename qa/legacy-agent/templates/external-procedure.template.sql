-- IBM Db2 13 for z/OS external procedure template (COBOL form).
-- Replace every {{TOKEN}}. The load module and package must be prepared
-- separately, and the selected WLM environment must be configured and authorized.

CREATE PROCEDURE {{PROCEDURE_SCHEMA}}.{{PROCEDURE_NAME}}
  (IN P_INPUT INTEGER,
   OUT P_OUTPUT INTEGER)
  SPECIFIC {{PROCEDURE_SCHEMA}}.{{PROCEDURE_NAME}}
  LANGUAGE COBOL
  EXTERNAL NAME {{LOAD_MODULE}}
  MODIFIES SQL DATA
  PARAMETER STYLE SQL
  DYNAMIC RESULT SETS {{MAX_RESULT_SETS}}
  COLLID {{PACKAGE_COLLECTION}}
  WLM ENVIRONMENT {{WLM_ENVIRONMENT}}
  PROGRAM TYPE {{PROGRAM_TYPE}}
  SECURITY {{EXTERNAL_SECURITY}}
  STAY RESIDENT {{STAY_RESIDENT}}
  COMMIT ON RETURN NO
  INHERIT SPECIAL REGISTERS;

-- Verification targets:
--   SYSIBM.SYSROUTINES.ROUTINETYPE = 'P', ORIGIN = 'E', LANGUAGE = 'COBOL'.
--   SYSIBM.SYSPARMS preserves parameter order, mode, type, and CCSID.
--   Registration success is separate from first-call proof of load-module,
--   package, WLM, Language Environment, and external-security readiness.
