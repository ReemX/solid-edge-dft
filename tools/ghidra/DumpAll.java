// Decompile every function and write one text file per program.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.io.*;

public class DumpAll extends GhidraScript {
    @Override
    public void run() throws Exception {
        String outDir = getScriptArgs()[0];
        String name = currentProgram.getName();
        DecompInterface d = new DecompInterface();
        d.toggleCCode(true); d.toggleSyntaxTree(false);
        d.openProgram(currentProgram);
        try (PrintWriter w = new PrintWriter(new BufferedWriter(new OutputStreamWriter(
                new FileOutputStream(new File(outDir, name + ".c")), "UTF-8")))) {
            FunctionIterator it = currentProgram.getFunctionManager().getFunctions(true);
            int n = 0;
            while (it.hasNext() && !monitor.isCancelled()) {
                Function f = it.next();
                if (f.isThunk() || f.isExternal()) continue;
                w.println("//@@FUNC " + f.getEntryPoint() + " " + f.getName(true));
                DecompileResults r = d.decompileFunction(f, 60, monitor);
                if (r != null && r.decompileCompleted()) w.println(r.getDecompiledFunction().getC());
                else w.println("// decompile failed");
                if (++n % 500 == 0) println("decompiled " + n);
            }
            println("done " + n);
        }
        // strings with xrefs
        try (PrintWriter w = new PrintWriter(new File(outDir, name + ".strings.txt"), "UTF-8")) {
            for (Data dt : currentProgram.getListing().getDefinedData(true)) {
                if (!dt.hasStringValue()) continue;
                StringBuilder sb = new StringBuilder();
                for (Reference ref : getReferencesTo(dt.getAddress())) {
                    Function f = getFunctionContaining(ref.getFromAddress());
                    sb.append(f == null ? ref.getFromAddress().toString() : f.getName()).append(' ');
                }
                w.println(dt.getAddress() + "\t" + String.valueOf(dt.getValue()).replace("\n","\n") + "\t" + sb);
            }
        }
    }
}
