"""Häufige Vornamen (klein geschrieben), um bei „Name“ Vor- und Nachname richtig zu trennen.

Beispiel: „Kochendörfer Kai“ -> Vorname Kai, Nachname Kochendörfer.
Fehlt ein Vorname, wird „Vorname Nachname“ angenommen. Die Liste darf gern ergänzt werden.
"""
VORNAMEN = set("""
aaron adam adrian ahmed aleksandra alena alex alexa alexander alexandra alexej ali alicia alina aline alisa alla
amelie ana anastasia andre andré andrea andreas andrej angela angelika anja anke ann anna annabell anne annette
anni annika antje anton antonia arne arnold artur astrid axel barbara bastian beate ben benedikt benjamin bernd
bernhard berthold bettina bianca birgit björn boris brigitte bruno burak can carina carl carla carmen carolin
caroline carsten celina chantal charlotte chiara christa christian christiane christina christine christoph
christopher clara claudia conny constanze cornelia daniel daniela danny david davide dean denis deniz dennis diana
dieter dietmar dirk dmitri dominik doris dorothea edith egon elena eleni elias elif elisabeth elke ella ellen elias
emil emilia emily emine emma emre enrico erik erika ernst esra eva evelyn fabian fabienne fatih fatma felix
finn florian frank franz franziska frederik frieda friedrich fritz gabi gabriele georg gerd gerda gerhard
gisela giuseppe gregor gudrun günter günther hakan hanna hannah hannelore hannes hans harald hasan heidi heike
heinrich heinz helena helga helmut hendrik henning henrik herbert hermann horst hubert hüseyin ibrahim ida ilona
ina ines inge ingo ingrid irene iris irina isabel isabell isabella ivan jakob jan jana janina janine jannik jasmin
jennifer jens jessica joachim jochen johann johanna johannes jonas jonathan josef joshua julia julian juliane
julius jürgen justin kai karin karina karl karsten katarina katharina kathrin katja katrin kemal kerstin kevin
kim klara klaus konrad konstantin kristina kurt lara larissa lars laura lea lena leon leonie lilli lina linda
lisa lorenz louis luca lucas luis luisa luise lukas luna lutz magdalena maik maike malte mandy manfred manuel
manuela marc marcel marco marcus maren margarete maria marian marie marina mario marion marius mark markus marlene
martin martina marvin mateo mathias matteo matthias max maximilian mehmet melanie melina melissa merve mia michael
michaela michelle mike milan mirko miriam mohamed mohammed monika moritz murat mustafa nadine nadja natalie
natascha nicole niklas nico nicolas nils nina noah nora norbert olaf oliver olga oskar pascal patricia patrick paul
paula peter petra philipp pia rainer ralf ralph rebecca regina reinhard renate rene rené richard rita robert robin
roland rolf roman ronja rosemarie ruth sabine sabrina sandra sara sarah sascha sebastian selin serkan silke simon
simone sina sofia sonja sophia sophie stefan stefanie steffen stephan stephanie sven svenja sylvia tanja tatjana
theo theresa thomas thorsten tilo tim timo tina tobias tom torsten udo ulf ulla ulrich ulrike ursula uta ute uwe
valentin vanessa vera verena viktor viktoria vincent volker walter waltraud werner wilhelm willi wolfgang yasemin
yusuf yvonne zoe
""".split())
