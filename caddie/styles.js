/* Yoink Caddie — client-side style engine.
   Crown demo pages embed course packs (#cpacks) and this script; it injects a
   style picker and re-dresses every hole from the same measurements. The Book
   is the locked brand default; Gen 11 restores the server-rendered Crown art.
   Choice persists per browser via localStorage. */
(function(){



function rng(seed){ var s=0; for(var i=0;i<seed.length;i++) s=(s*31+seed.charCodeAt(i))>>>0;
  return function(){ s=(s+0x6D2B79F5)>>>0; var t=Math.imul(s^(s>>>15),1|s);
    t=(t+Math.imul(t^(t>>>7),61|t))^t; return ((t^(t>>>14))>>>0)/4294967296; }; }
function smooth(pts, closed){
  var p=pts.slice(); if(closed && (p[0][0]!==p[p.length-1][0]||p[0][1]!==p[p.length-1][1])) p.push(p[0]);
  if(closed) p.pop();
  var n=p.length, d='M'+p[0][0].toFixed(1)+','+p[0][1].toFixed(1);
  function at(i){ return p[((i%n)+n)%n]; }
  var end=closed?n:n-1;
  for(var i=0;i<end;i++){
    var p0=at(i-1),p1=at(i),p2=at(i+1),p3=at(i+2);
    if(!closed){ if(i===0)p0=p1; if(i===n-2)p3=p2; }
    var c1=[p1[0]+(p2[0]-p0[0])/6, p1[1]+(p2[1]-p0[1])/6];
    var c2=[p2[0]-(p3[0]-p1[0])/6, p2[1]-(p3[1]-p1[1])/6];
    d+='C'+c1[0].toFixed(1)+','+c1[1].toFixed(1)+' '+c2[0].toFixed(1)+','+c2[1].toFixed(1)+' '+p2[0].toFixed(1)+','+p2[1].toFixed(1);
  }
  return d+(closed?'Z':'');
}
var segs=[], totalLen=0;
function rebuildArc(){ segs=[]; totalLen=0; for(var i=0;i<G.line.length-1;i++){ var a=G.line[i],b=G.line[i+1];
  var L=Math.hypot(b[0]-a[0],b[1]-a[1]); segs.push({a:a,b:b,L:L}); totalLen+=L; } }
function lineAt(arc){ var t=Math.max(0,Math.min(arc,totalLen)), i=0;
  while(i<segs.length-1 && t>segs[i].L){ t-=segs[i].L; i++; }
  var s=segs[i], f=t/s.L;
  return { p:[s.a[0]+(s.b[0]-s.a[0])*f, s.a[1]+(s.b[1]-s.a[1])*f],
           d:[(s.b[0]-s.a[0])/s.L,(s.b[1]-s.a[1])/s.L] }; }
function corridor(a0,a1,wFn,R){
  var left=[], right=[], steps=26;
  for(var i=0;i<=steps;i++){
    var arc=a0+(a1-a0)*i/steps, q=lineAt(arc), w=wFn(arc)*(0.94+(R?R():0.5)*0.12);
    left.push([q.p[0]-q.d[1]*w, q.p[1]+q.d[0]*w]);
    right.push([q.p[0]+q.d[1]*w, q.p[1]-q.d[0]*w]);
  }
  return left.concat(right.reverse());
}
function fwWidth(arc){ var t=(arc-G.fwStart)/(totalLen-G.fwStart);
  return 15+14*Math.sin(Math.min(1,Math.max(0,t))*Math.PI)*1.05; }
function treeSpots(R){
  var out=[];
  G.stands.forEach(function(st){
    var n=Math.max(2,st.count+1);
    for(var i=0;i<n;i++){
      var arc=st.a0+(st.a1-st.a0)*(i+0.5)/n, q=lineAt(arc);
      var off=st.d+6+R()*10;
      out.push([q.p[0]+q.d[1]*off*st.side*-1, q.p[1]-q.d[0]*off*st.side*-1, 8+R()*7]);
    }
  });
  return out;
}
function inset(pts, f){
  var cx=0, cy=0; pts.forEach(function(p){cx+=p[0];cy+=p[1];});
  cx/=pts.length; cy/=pts.length;
  return pts.map(function(p){ return [cx+(p[0]-cx)*f, cy+(p[1]-cy)*f]; });
}




var G=null;   // page-space geometry, set per hole by renderBook

function renderBook(el, H, meta){
  var target=el.id || (el.id='ha'+H.hole);
  var INK='#14432A', MUT='#6D7770', FAINT='#9AA39C', ACID='#C7F24A', PENCIL='#55584F', TREE='#D6E0BE';
  var SUF='_'+target;
  var R=rng((meta.key||'course')+':'+H.hole+':book');

  // ---- fit raw yards geometry into the page art zone ----
  var pts=[];
  function eat(a){ (a||[]).forEach(function(p){ pts.push(p); }); }
  eat(H.line); eat(H.green); eat(H.tees);
  (H.bunkers||[]).forEach(eat); (H.waters||[]).forEach(eat);
  var xs=pts.map(function(p){return p[0];}), ys=pts.map(function(p){return p[1];});
  var minx=Math.min.apply(0,xs)-18, maxx=Math.max.apply(0,xs)+18;
  var miny=Math.min.apply(0,ys)-14, maxy=Math.max.apply(0,ys)+6;
  var s=Math.min(226/(maxx-minx), 484/(maxy-miny), H.par===3?2.1:1.35);
  var tx=-20-s*(minx+maxx)/2, ty=-16-s*maxy;
  function T(p){ return [p[0]*s+tx, p[1]*s+ty]; }
  function Tp(a){ return (a||[]).map(T); }

  G={ line:Tp(H.line), green:Tp(H.green), tees:Tp(H.tees),
      bunkers:(H.bunkers||[]).map(Tp), waters:(H.waters||[]).map(Tp),
      stands:(H.stands||[]).map(function(st){ return {d:st.d*s, a0:st.a0*s, a1:st.a1*s, side:st.side, count:st.count}; }),
      fwStart:(H.fw_start!=null?H.fw_start*s:null), bendAt:(H.bend?H.bend.at*s:null) };
  rebuildArc();

  var defs = "<defs>"
    +"<pattern id='bkgrid"+SUF+"' width='11' height='11' patternUnits='userSpaceOnUse'><path d='M11,0 L0,0 0,11' fill='none' stroke='#E4E1D2' stroke-width='0.5'/></pattern>"
    +"<filter id='bkpencil"+SUF+"'><feTurbulence type='fractalNoise' baseFrequency='0.09' numOctaves='2' seed='31'/><feDisplacementMap in='SourceGraphic' scale='1.6'/></filter>"
    +"<clipPath id='bkclip"+SUF+"'><rect x='24' y='-188' width='72' height='72'/></clipPath>"
    +"</defs>";
  var s2 = "<rect x='-155' y='-565' width='260' height='615' fill='#F6F4EB'/>";
  s2 += "<rect x='-136' y='-565' width='241' height='615' fill='url(#bkgrid"+SUF+")'/>";
  for(var i=0;i<13;i++){
    var y=-548+i*47;
    s2 += "<circle cx='-147' cy='"+y+"' r='3.4' fill='#F6F4EB' stroke='"+FAINT+"' stroke-width='1.2'/>";
    s2 += "<path d='M-147,"+(y-3.4)+" A6,6 0 0 1 -141,"+y+"' fill='none' stroke='"+MUT+"' stroke-width='1.4'/>";
  }
  s2 += "<line x1='-136' y1='-565' x2='-136' y2='50' stroke='#D9D5C4' stroke-width='0.8'/>";

  // ---- hole art ----
  if(G.fwStart!=null){
    s2 += "<path d='"+smooth(corridor(16*s,G.fwStart,function(a){return 12*s;},null),true)+"' fill='none' stroke='"+INK+"' stroke-width='0.7' stroke-dasharray='2 2.6' opacity='0.55'/>";
    var fwd = smooth(corridor(G.fwStart,totalLen-8*s,fwWidth,null),true);
    s2 += "<path d='"+fwd+"' fill='#EAEFE0' stroke='"+INK+"' stroke-width='1'/>";
  }
  G.waters.forEach(function(w){
    s2 += "<path d='"+smooth(w,true)+"' fill='#DEE9EA' stroke='"+INK+"' stroke-width='1.1'/>";
    s2 += "<path d='"+smooth(inset(w.slice(0,-1),0.72),true)+"' fill='none' stroke='#9CBEC2' stroke-width='0.6'/>";
    s2 += "<path d='"+smooth(inset(w.slice(0,-1),0.45),true)+"' fill='none' stroke='#9CBEC2' stroke-width='0.5' opacity='0.7'/>";
  });
  G.bunkers.forEach(function(b){
    s2 += "<path d='"+smooth(b,true)+"' fill='#F0EAD6' stroke='"+INK+"' stroke-width='0.9'/>";
  });
  s2 += "<path d='"+smooth(G.green,true)+"' fill='#DCE7CE' stroke='"+INK+"' stroke-width='1.4'/>";
  var pin=T([ (H.green.reduce(function(a,p){return a+p[0];},0)/H.green.length),
              (H.green.reduce(function(a,p){return a+p[1];},0)/H.green.length) ]);
  s2 += "<circle cx='"+pin[0].toFixed(1)+"' cy='"+pin[1].toFixed(1)+"' r='2.2' fill='"+ACID+"' stroke='"+INK+"' stroke-width='0.9'/>";
  G.tees.forEach(function(t){ s2 += "<rect x='"+(t[0]-3).toFixed(1)+"' y='"+(t[1]-1.8).toFixed(1)+"' width='6' height='3.6' fill='none' stroke='"+INK+"' stroke-width='0.9'/>"; });
  var trs=Math.min(1.15,Math.max(0.8,s));
  treeSpots(R).forEach(function(t){
    t[2]=t[2]*trs;
    var ell = "<ellipse cx='"+t[0].toFixed(1)+"' cy='"+t[1].toFixed(1)+"' rx='"+(t[2]*1.05).toFixed(1)+"' ry='"+(t[2]*0.5).toFixed(1)+"'/>"
      +"<ellipse cx='"+(t[0]-t[2]*0.55).toFixed(1)+"' cy='"+(t[1]+2.6).toFixed(1)+"' rx='"+(t[2]*0.55).toFixed(1)+"' ry='"+(t[2]*0.3).toFixed(1)+"'/>"
      +"<ellipse cx='"+(t[0]+t[2]*0.55).toFixed(1)+"' cy='"+(t[1]+3).toFixed(1)+"' rx='"+(t[2]*0.5).toFixed(1)+"' ry='"+(t[2]*0.28).toFixed(1)+"'/>";
    s2 += "<g stroke='"+INK+"' stroke-width='1.8' fill='"+TREE+"'>"+ell+"</g>";
    s2 += "<g fill='"+TREE+"' stroke='none'>"+ell+"</g>";
  });
  // the line: single dashed ink, arrowhead at the green
  s2 += "<path d='"+smooth(G.line,false)+"' fill='none' stroke='"+INK+"' stroke-width='1.7' stroke-dasharray='8 5' stroke-linecap='round'/>";
  var tip=lineAt(totalLen), bk=lineAt(totalLen-6);
  var dx=tip.p[0]-bk.p[0], dy=tip.p[1]-bk.p[1], dl=Math.hypot(dx,dy)||1; dx/=dl; dy/=dl;
  var ax=tip.p[0], ay=tip.p[1];
  s2 += "<path d='M"+(ax-4*dx-3*dy).toFixed(1)+","+(ay-4*dy+3*dx).toFixed(1)+" L"+ax.toFixed(1)+","+ay.toFixed(1)
      +" L"+(ax-4*dx+3*dy).toFixed(1)+","+(ay-4*dy-3*dx).toFixed(1)+"' fill='none' stroke='"+INK+"' stroke-width='1.3'/>";
  // pips each 100 yards
  for(var a=100; a<H.total-24; a+=100){
    var q=lineAt(a*s).p;
    s2 += "<circle cx='"+q[0].toFixed(1)+"' cy='"+q[1].toFixed(1)+"' r='2.2' fill='#F6F4EB' stroke='"+INK+"' stroke-width='0.9'/>";
    s2 += "<text x='"+(q[0]-6.5).toFixed(1)+"' y='"+(q[1]+2.2).toFixed(1)+"' font-size='6.2' font-family='Archivo, sans-serif' font-weight='700' fill='"+MUT+"' text-anchor='end'>"+a+"</text>";
  }
  function tick(arcY,label){
    var q=lineAt(arcY*s), w=(G.fwStart!=null?fwWidth(arcY*s):12*s)+7, pp=[q.d[1],-q.d[0]];
    var x1=q.p[0]-pp[0]*w, y1=q.p[1]-pp[1]*w, x2=q.p[0]+pp[0]*w, y2=q.p[1]+pp[1]*w;
    return "<path d='M"+x1.toFixed(1)+","+y1.toFixed(1)+" L"+x2.toFixed(1)+","+y2.toFixed(1)+"' stroke='"+INK+"' stroke-width='0.7' stroke-dasharray='2 2'/>"
      +"<text x='"+(x2+4).toFixed(1)+"' y='"+(y2+2.2).toFixed(1)+"' font-size='7' font-family='Archivo, sans-serif' font-weight='700' fill='"+INK+"'>"+label+"</text>";
  }
  if(H.fw_start!=null) s2 += tick(H.fw_start, H.fw_start+' FWY');
  if(H.bend && Math.abs(H.bend.at-(H.fw_start||-999))>18) s2 += tick(H.bend.at, H.bend.at+' TURN');
  // carry notes, right margin
  (H.carries||[]).forEach(function(c){
    if(c.kind==='fairway') return;
    if(c.kind==='sand' && c.at>H.total-30) return;
    var q=lineAt(c.at*s).p;
    var yy=Math.max(-500,Math.min(-30,q[1]));
    s2 += "<text x='96' y='"+yy.toFixed(1)+"' font-size='7' font-family='Archivo, sans-serif' font-weight='700' fill='"+INK+"' text-anchor='end'>CARRY "+c.at+" &#183; "+c.kind.toUpperCase()+"</text>";
  });
  // pencil live note (par 4/5): mid-approach position
  if(H.par>3){
    var frac=0.62, me=lineAt(totalLen*frac).p, rem=Math.round(H.total*(1-frac));
    s2 += "<circle cx='"+me[0].toFixed(1)+"' cy='"+me[1].toFixed(1)+"' r='2.6' fill='"+ACID+"' stroke='"+INK+"' stroke-width='1'/>";
    s2 += "<g filter='url(#bkpencil"+SUF+")'>";
    s2 += "<circle cx='-105' cy='"+(me[1]-2).toFixed(1)+"' r='13' fill='none' stroke='"+PENCIL+"' stroke-width='1.3'/>";
    s2 += "<path d='M-92,"+(me[1]-2).toFixed(1)+" L"+(me[0]-6).toFixed(1)+","+(me[1]-0.5).toFixed(1)+"' stroke='"+PENCIL+"' stroke-width='0.9' fill='none'/>";
    s2 += "</g>";
    s2 += "<text x='-105' y='"+(me[1]+3).toFixed(1)+"' font-size='13' font-family='Caveat, cursive' font-weight='600' fill='"+PENCIL+"' text-anchor='middle'>"+rem+"</text>";
    s2 += "<text x='-105' y='"+(me[1]-19).toFixed(1)+"' font-size='9' font-family='Caveat, cursive' fill='"+PENCIL+"' text-anchor='middle'>to ctr</text>";
  }
  // green detail box
  var gs=0, gc=pin;
  (function(){
    var gxs=H.green.map(function(p){return p[0];}), gys=H.green.map(function(p){return p[1];});
    var gw=Math.max.apply(0,gxs)-Math.min.apply(0,gxs), gh=Math.max.apply(0,gys)-Math.min.apply(0,gys);
    gs=52/Math.max(gw,gh);
    var rawc=[(Math.max.apply(0,gxs)+Math.min.apply(0,gxs))/2,(Math.max.apply(0,gys)+Math.min.apply(0,gys))/2];
    s2 += "<rect x='24' y='-188' width='72' height='72' fill='#FBFAF4' stroke='"+INK+"' stroke-width='1.1'/>";
    s2 += "<rect x='24' y='-188' width='72' height='72' fill='url(#bkgrid"+SUF+")'/>";
    s2 += "<g clip-path='url(#bkclip"+SUF+")'><g transform='translate(60,-152) scale("+gs.toFixed(3)+") translate("+(-rawc[0]).toFixed(1)+","+(-rawc[1]).toFixed(1)+")'>";
    s2 += "<path d='"+smooth(H.green,true)+"' fill='#DCE7CE' stroke='"+INK+"' stroke-width='"+(1.2/gs).toFixed(2)+"'/>";
    (H.bunkers||[]).forEach(function(b){
      var bc=[b.reduce(function(a,p){return a+p[0];},0)/b.length, b.reduce(function(a,p){return a+p[1];},0)/b.length];
      if(Math.hypot(bc[0]-rawc[0],bc[1]-rawc[1])<42)
        s2 += "<path d='"+smooth(b,true)+"' fill='#F0EAD6' stroke='"+INK+"' stroke-width='"+(0.8/gs).toFixed(2)+"'/>";
    });
    s2 += "<circle cx='"+rawc[0].toFixed(1)+"' cy='"+rawc[1].toFixed(1)+"' r='"+(1.8/gs).toFixed(2)+"' fill='"+ACID+"' stroke='"+INK+"' stroke-width='"+(0.7/gs).toFixed(2)+"'/>";
    s2 += "</g></g>";
  })();
  s2 += "<text x='60' y='-106' font-size='6.4' font-family='Archivo, sans-serif' font-weight='700' letter-spacing='0.8' fill='"+INK+"' text-anchor='middle'>GREEN &#183; "+(H.depth||'?')+" DEEP</text>";

  // header
  var bkNm=(meta.name||'THE BOOK')
    .replace(/\s+(state park|country club|golf course|golf club|golf links|golf center|park golf course)$/i,'')
    .toUpperCase().slice(0,26);
  var bkFs=Math.max(6.5, Math.min(9.5, (125/Math.max(1,bkNm.length)-1.8)/0.62));
  var hn=(H.hole<10?'0':'')+H.hole;
  s2 += "<rect x='-128' y='-556' width='30' height='30' fill='none' stroke='"+INK+"' stroke-width='1.4'/>";
  s2 += "<text x='-113' y='-533' font-size='"+(H.hole<10?22:18)+"' font-family='Archivo, sans-serif' font-weight='900' fill='"+INK+"' text-anchor='middle'>"+H.hole+"</text>";
  s2 += "<g font-family='Archivo, sans-serif'>";
  s2 += "<text x='-90' y='-544' font-size='"+bkFs.toFixed(1)+"' font-weight='700' letter-spacing='1.8' fill='"+INK+"'>"+bkNm+"</text>";
  s2 += "<text x='-90' y='-532' font-size='6.6' font-weight='700' letter-spacing='1' fill='"+MUT+"'>YOINK &#183; THE BOOK</text>";
  s2 += "<text x='96' y='-544' font-size='6.4' font-weight='700' fill='"+FAINT+"' text-anchor='end'>PAGE "+hn+" / 18</text>";
  s2 += "</g>";
  s2 += "<line x1='-128' y1='-524' x2='-46' y2='-524' stroke='"+INK+"' stroke-width='1'/>";
  var vfs=Math.min(10.5, 216/(0.42*H.sign.length));
  s2 += "<text x='-128' y='0' font-size='"+vfs.toFixed(1)+"' font-family='Caveat, cursive' font-weight='600' fill='"+PENCIL+"'>"+H.sign+"</text>";

  // scorecard strip
  var cols=[['HOLE',''+H.hole,22],['PAR',''+H.par,22],['HCP','&#8212;',22],['BACK',''+H.yards.back,30],['MID',''+H.yards.mid,30],['FWD',''+H.yards.front,30],['SCORE','',46]];
  var x0=-128, y0=8, hh=32, tot=0; cols.forEach(function(c){tot+=c[2];});
  s2 += "<rect x='"+x0+"' y='"+y0+"' width='"+tot+"' height='"+hh+"' fill='#FBFAF4' stroke='"+INK+"' stroke-width='1.2'/>";
  var cx=x0;
  cols.forEach(function(c,i){
    if(i>0) s2 += "<line x1='"+cx+"' y1='"+y0+"' x2='"+cx+"' y2='"+(y0+hh)+"' stroke='"+INK+"' stroke-width='0.7'/>";
    s2 += "<text x='"+(cx+c[2]/2)+"' y='"+(y0+10)+"' font-size='5.6' font-family='Archivo, sans-serif' font-weight='700' letter-spacing='0.8' fill='"+MUT+"' text-anchor='middle'>"+c[0]+"</text>";
    if(c[1]) s2 += "<text x='"+(cx+c[2]/2)+"' y='"+(y0+25)+"' font-size='11.5' font-family='Archivo, sans-serif' font-weight='900' fill='"+INK+"' text-anchor='middle'>"+c[1]+"</text>";
    cx+=c[2];
  });
  s2 += "<line x1='"+x0+"' y1='"+(y0+14)+"' x2='"+(x0+tot)+"' y2='"+(y0+14)+"' stroke='"+INK+"' stroke-width='0.6'/>";
  s2 += "<g transform='translate(88,14) scale(0.16)'><path d='M50,5 c4.4,0 7.3,3.4 6.9,7.7 L52.7,103 h-5.4 L43.1,12.7 C42.7,8.4 45.6,5 50,5 Z' fill='"+INK+"'/><path d='M56.6,11 l31,9.6 -31,9.6 z' fill='"+ACID+"'/><circle cx='50' cy='125.5' r='9.6' fill='"+INK+"'/></g>";

  el.setAttribute('viewBox','-155 -565 260 615'); el.innerHTML=defs+s2;
}




// ---- shared page fit for the framed styles (Estate / Landform / Evening) ----
function stripName(n){
  return String(n).replace(/\s+(state park|country club|golf course|golf club|golf links|golf center|park golf course|golf and tennis club|golf and country club)$/i,'')
    .toUpperCase().slice(0,26);
}
function fitPage(H){
  var pts=[];
  function eat(a){ (a||[]).forEach(function(p){ pts.push(p); }); }
  eat(H.line); eat(H.green); eat(H.tees);
  (H.bunkers||[]).forEach(eat); (H.waters||[]).forEach(eat);
  var xs=pts.map(function(p){return p[0];}), ys=pts.map(function(p){return p[1];});
  var minx=Math.min.apply(0,xs)-20, maxx=Math.max.apply(0,xs)+20;
  var miny=Math.min.apply(0,ys)-16, maxy=Math.max.apply(0,ys)+6;
  var s=Math.min(212/(maxx-minx), 452/(maxy-miny), H.par===3?2.0:1.3);
  var tx=-24-s*(minx+maxx)/2, ty=-64-s*maxy;
  function T(p){ return [p[0]*s+tx, p[1]*s+ty]; }
  function Tp(a){ return (a||[]).map(T); }
  G={ line:Tp(H.line), green:Tp(H.green), tees:Tp(H.tees),
      bunkers:(H.bunkers||[]).map(Tp), waters:(H.waters||[]).map(Tp),
      stands:(H.stands||[]).map(function(st){ return {d:st.d*s, a0:st.a0*s, a1:st.a1*s, side:st.side, count:st.count}; }),
      fwStart:(function(){ var f=(H.fw_start!=null)?H.fw_start:(H.fw&&H.fw[0]?H.fw[0][0]:null); return f!=null?f*s:null; })(), bendAt:(H.bend?H.bend.at*s:null) };
  rebuildArc();
  return s;
}

function renderEstate(el,H,meta){
  var s_=fitPage(H);
  var SUF='_'+el.id;
  var safeFw=(G.fwStart!=null)?fwWidth:function(a){return 13;};
  var R=rng((meta.key||'c')+':'+H.hole+':estate');
  var PAPER='#F3EDDD', PLATE='#CBC2A8', INK='#243B2E', WATER='#3E5A64', GOLD='#A98B2D';
  var defs="<defs>"
    +"<pattern id='eh1"+SUF+"' width='3.6' height='3.6' patternUnits='userSpaceOnUse' patternTransform='rotate(37)'><line x1='0' y1='0' x2='0' y2='3.6' stroke='"+INK+"' stroke-width='0.5' opacity='0.55'/></pattern>"
    +"<pattern id='eh2"+SUF+"' width='3.2' height='3.2' patternUnits='userSpaceOnUse' patternTransform='rotate(-49)'><line x1='0' y1='0' x2='0' y2='3.2' stroke='"+INK+"' stroke-width='0.45' opacity='0.5'/></pattern>"
    +"<pattern id='eh3"+SUF+"' width='6.5' height='6.5' patternUnits='userSpaceOnUse' patternTransform='rotate(37)'><line x1='0' y1='0' x2='0' y2='6.5' stroke='"+INK+"' stroke-width='0.4' opacity='0.35'/></pattern>"
    +"<pattern id='estip"+SUF+"' width='4.4' height='4.4' patternUnits='userSpaceOnUse'><circle cx='1' cy='1.2' r='0.5' fill='"+INK+"' opacity='0.55'/><circle cx='3.1' cy='3.3' r='0.42' fill='"+INK+"' opacity='0.45'/><circle cx='2.2' cy='0.4' r='0.3' fill='"+INK+"' opacity='0.3'/></pattern>"
    +"<filter id='ewob"+SUF+"'><feTurbulence type='fractalNoise' baseFrequency='0.11' numOctaves='2' seed='4'/><feDisplacementMap in='SourceGraphic' scale='1.1'/></filter>"
    +"</defs>";
var ORD=['First','Second','Third','Fourth','Fifth','Sixth','Seventh','Eighth','Ninth','Tenth','Eleventh','Twelfth','Thirteenth','Fourteenth','Fifteenth','Sixteenth','Seventeenth','Eighteenth'];
  var estNm=stripName(meta.name||'THE COURSE');
  var estFs=Math.max(7,Math.min(12.5,(148/Math.max(1,estNm.length)-3.2)/0.62));
  var s="<rect x='-155' y='-565' width='260' height='615' fill='"+PAPER+"'/>";
  // plate mark + ruled border
  s+="<rect x='-146' y='-556' width='242' height='597' fill='none' stroke='"+PLATE+"' stroke-width='1.6'/>";
  s+="<rect x='-140' y='-550' width='230' height='585' fill='none' stroke='"+INK+"' stroke-width='1.1'/>";
  s+="<rect x='-137' y='-547' width='224' height='579' fill='none' stroke='"+INK+"' stroke-width='0.35'/>";

  // rough: double-hatched ground, fairway carved out of it
  var roughD=smooth(corridor(4,totalLen,function(a){return safeFw(a)+23;},R),true);
  s+="<g filter='url(#ewob"+SUF+")'>";
  s+="<path d='"+roughD+"' fill='url(#eh1"+SUF+")'/>";
  s+="<path d='"+roughD+"' fill='url(#eh2"+SUF+")'/>";
  s+="<path d='"+roughD+"' fill='none' stroke='"+INK+"' stroke-width='0.8'/>";
  if(G.fwStart!=null){
    var fwD=smooth(corridor(G.fwStart,totalLen-8,safeFw,null),true);
    s+="<path d='"+fwD+"' fill='"+PAPER+"'/>";
    s+="<path d='"+fwD+"' fill='url(#eh3"+SUF+")'/>";
    s+="<path d='"+fwD+"' fill='none' stroke='"+INK+"' stroke-width='0.9'/>";
  }
  s+="</g>";
  // approach/walk before the fairway: pale stipple path
  s+="<path d='"+smooth(corridor(14,(G.fwStart!=null?G.fwStart+6:totalLen*0.55),function(a){return 8;},null),true)+"' fill='url(#estip"+SUF+")' opacity='0.35'/>";

  // water: engraved concentric shorelines
  G.waters.forEach(function(w){
    s+="<g filter='url(#ewob"+SUF+")'>";
    s+="<path d='"+smooth(w,true)+"' fill='"+PAPER+"' stroke='"+WATER+"' stroke-width='1.1'/>";
    [0.92,0.82,0.71,0.59,0.46,0.32,0.18].forEach(function(f,i){
      s+="<path d='"+smooth(inset(w.slice(0,-1),f),true)+"' fill='none' stroke='"+WATER+"' stroke-width='"+(0.7-i*0.06)+"' opacity='"+(0.85-i*0.1)+"'/>";
    });
    s+="</g>";
  });
  // bunkers: stipple with a lipped edge
  G.bunkers.forEach(function(b){
    s+="<g filter='url(#ewob"+SUF+")'><path d='"+smooth(b,true)+"' fill='url(#estip"+SUF+")' stroke='"+INK+"' stroke-width='0.9'/>";
    s+="<path d='"+smooth(inset(b.slice(0,-1),0.6),true)+"' fill='none' stroke='"+INK+"' stroke-width='0.4' opacity='0.5'/></g>";
  });
  // green: contour-hatched putting surface
  s+="<g filter='url(#ewob"+SUF+")'>";
  s+="<path d='"+smooth(G.green,true)+"' fill='"+PAPER+"' stroke='"+INK+"' stroke-width='1.2'/>";
  [0.78,0.55,0.32].forEach(function(f){
    s+="<path d='"+smooth(inset(G.green.slice(0,-1),f),true)+"' fill='none' stroke='"+INK+"' stroke-width='0.45' opacity='0.55'/>";
  });
  s+="</g>";
  // pin: gilded
  var gp=lineAt(totalLen).p;
  s+="<line x1='"+gp[0]+"' y1='"+gp[1]+"' x2='"+gp[0]+"' y2='"+(gp[1]-13)+"' stroke='"+INK+"' stroke-width='0.9'/>";
  s+="<path d='M"+gp[0]+","+(gp[1]-13)+" l7.5,2.6 -7.5,2.6 z' fill='"+GOLD+"' stroke='"+INK+"' stroke-width='0.5'/>";
  s+="<circle cx='"+gp[0]+"' cy='"+gp[1]+"' r='1.5' fill='"+GOLD+"' stroke='"+INK+"' stroke-width='0.6'/>";

  // trees: antique estate rounds — scalloped crown, SE shade
  treeSpots(R).forEach(function(t){
    var x=t[0],y=t[1],r=t[2]*0.92;
    var d='', n=9;
    for(var i=0;i<n;i++){ var a0=i/n*Math.PI*2, a1=(i+1)/n*Math.PI*2;
      var mx=x+Math.cos((a0+a1)/2)*r*1.24, my=y+Math.sin((a0+a1)/2)*r*0.72;
      var x1=x+Math.cos(a1)*r, y1=y+Math.sin(a1)*r*0.58;
      d+=(i===0?('M'+(x+r)+','+y):'')+' Q'+mx.toFixed(1)+','+my.toFixed(1)+' '+x1.toFixed(1)+','+y1.toFixed(1);
    }
    s+="<g filter='url(#ewob"+SUF+")'><path d='"+d+"' fill='"+PAPER+"' stroke='"+INK+"' stroke-width='0.9'/>";
    for(var k=0;k<4;k++){
      var f=0.25+k*0.16;
      s+="<path d='M"+(x+r*f*0.5)+","+(y+r*0.5*f+1)+" q"+(r*0.45)+","+(r*0.28)+" "+(r*(0.95-f*0.4))+","+(r*0.12)+"' fill='none' stroke='"+INK+"' stroke-width='0.4' opacity='0.6'/>";
    }
    s+="<circle cx='"+x+"' cy='"+(y+1)+"' r='0.8' fill='"+INK+"'/></g>";
  });
  // tees: small engraved rectangles
  G.tees.forEach(function(t){ s+="<rect x='"+(t[0]-3.6)+"' y='"+(t[1]-2)+"' width='7.2' height='4' fill='url(#eh3"+SUF+")' stroke='"+INK+"' stroke-width='0.7'/>"; });

  // the line of play: fine dash, oldstyle numerals
  s+="<path d='"+smooth(G.line,false)+"' fill='none' stroke='"+INK+"' stroke-width='0.7' stroke-dasharray='5 3.4'/>";
  var pips=[]; for(var pa=100; pa<H.total-24; pa+=100) pips.push(pa);
  pips.forEach(function(a){ var q=lineAt(a*s_).p;
    s+="<circle cx='"+q[0]+"' cy='"+q[1]+"' r='1.4' fill='"+PAPER+"' stroke='"+INK+"' stroke-width='0.7'/>";
    s+="<text x='"+(q[0]-5.5)+"' y='"+(q[1]+2.4)+"' font-size='6.8' font-family='Fraunces, Georgia, serif' font-style='italic' fill='"+INK+"' text-anchor='end'>"+a+"</text>"; });

  // cartouche
  s+="<g>";
  s+="<path d='M-84,-24 L58,-24 L64,-18 L64,26 L58,32 L-84,32 L-90,26 L-90,-18 Z' fill='"+PAPER+"' stroke='"+INK+"' stroke-width='1.1'/>";
  s+="<path d='M-86,-20 L60,-20 L60,28 L-86,28 Z' fill='none' stroke='"+INK+"' stroke-width='0.4'/>";
  s+="<text x='-13' y='-6' font-size='"+estFs.toFixed(1)+"' font-family='Fraunces, Georgia, serif' font-weight='600' letter-spacing='3.2' fill='"+INK+"' text-anchor='middle'>"+estNm+"</text>";
  s+="<line x1='-56' y1='1.5' x2='30' y2='1.5' stroke='"+GOLD+"' stroke-width='1'/>";
  s+="<circle cx='-13' cy='1.5' r='1.8' fill='"+GOLD+"'/>";
  s+="<text x='-13' y='13' font-size='7.5' font-family='Fraunces, Georgia, serif' font-style='italic' letter-spacing='1.4' fill='"+INK+"' text-anchor='middle'>Hole the "+(ORD[H.hole-1]||H.hole)+" &#183; Par "+H.par+" &#183; "+H.yards.mid+" Yards</text>";
  s+="<text x='-13' y='24' font-size='5.6' font-family='Archivo, sans-serif' font-weight='700' letter-spacing='2.4' fill='"+GOLD+"' text-anchor='middle'>SURVEYED &amp; ENGRAVED FOR YOINK</text>";
  s+="</g>";
  // hole number, top right, engraved roundel
  s+="<circle cx='78' cy='-528' r='15' fill='"+PAPER+"' stroke='"+INK+"' stroke-width='1.1'/>";
  s+="<circle cx='78' cy='-528' r='12.2' fill='none' stroke='"+GOLD+"' stroke-width='0.9'/>";
  s+="<text x='78' y='-520.5' font-size='"+(H.hole>9?15:19)+"' font-family='Fraunces, Georgia, serif' font-weight='600' fill='"+INK+"' text-anchor='middle'>"+H.hole+"</text>";
  el.setAttribute('viewBox','-155 -565 260 615'); el.innerHTML=defs+s;

}
function renderLandform(el,H,meta){
  var s_=fitPage(H);
  var SUF='_'+el.id;
  var safeFw=(G.fwStart!=null)?fwWidth:function(a){return 13;};
  var R=rng((meta.key||'c')+':'+H.hole+':landform');
  var FIELD='#0E1811', B1='#1A291D', B2='#25382A', B3='#324939', B4='#405C48', FW='#5C7D5B', GN='#7FA379', SAND='#C7AE79', WAT='#17313B', ACID='#C7F24A';
  var defs="<defs>"
    +"<filter id='lfsh1"+SUF+"' x='-40%' y='-40%' width='180%' height='180%'><feDropShadow dx='0' dy='4' stdDeviation='5' flood-color='#000000' flood-opacity='0.55'/></filter>"
    +"<filter id='lfsh2"+SUF+"' x='-40%' y='-40%' width='180%' height='180%'><feDropShadow dx='0' dy='3' stdDeviation='3.5' flood-color='#000000' flood-opacity='0.5'/></filter>"
    +"<filter id='lfsh3"+SUF+"' x='-40%' y='-40%' width='180%' height='180%'><feDropShadow dx='0' dy='2' stdDeviation='2' flood-color='#000000' flood-opacity='0.45'/></filter>"
    +"<linearGradient id='lfw"+SUF+"' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='#224653'/><stop offset='1' stop-color='#122730'/></linearGradient>"
    +"<radialGradient id='lfvig"+SUF+"' cx='0.5' cy='0.42' r='0.75'><stop offset='0.62' stop-color='#000000' stop-opacity='0'/><stop offset='1' stop-color='#000000' stop-opacity='0.4'/></radialGradient>"
    +"</defs>";
  var lfNm=stripName(meta.name||'THE COURSE');
  var s="<rect x='-155' y='-565' width='260' height='615' fill='"+FIELD+"'/>";
  function band(pad, fill, filt){
    var d=smooth(corridor((G.fwStart!=null?Math.max(2,G.fwStart-(pad*26)):2), totalLen, function(a){return safeFw(a)+pad*9;}, null),true);
    return "<g filter='url(#"+filt+")'><path d='"+d+"' fill='"+fill+"'/><path d='"+d+"' fill='none' stroke='#B8D4A8' stroke-width='1' opacity='0.10'/></g>";
  }
  s+=band(3.4,B2,'lfsh1');
  s+=band(2.4,B3,'lfsh2');
  s+=band(1.5,B4,'lfsh2');
  // fairway plateau
  if(G.fwStart!=null){
    var fwD=smooth(corridor(G.fwStart,totalLen-8,safeFw,null),true);
    s+="<g filter='url(#lfsh3"+SUF+")'><path d='"+fwD+"' fill='"+FW+"'/><path d='"+fwD+"' fill='none' stroke='#CFE4BC' stroke-width='1' opacity='0.16'/></g>";
  }
  // water: recessed
  G.waters.forEach(function(w){
    var d=smooth(w,true);
    s+="<path d='"+d+"' fill='url(#lfw"+SUF+")'/>";
    s+="<path d='"+smooth(inset(w.slice(0,-1),0.9),true)+"' fill='none' stroke='#000000' stroke-width='2.6' opacity='0.35'/>";
    s+="<path d='"+d+"' fill='none' stroke='#6FA3AF' stroke-width='0.8' opacity='0.5'/>";
  });
  // bunkers: raised dishes
  G.bunkers.forEach(function(b){
    s+="<g filter='url(#lfsh3"+SUF+")'><path d='"+smooth(b,true)+"' fill='"+SAND+"'/></g>";
    s+="<path d='"+smooth(inset(b.slice(0,-1),0.55),true)+"' fill='none' stroke='#8F7A4C' stroke-width='0.8' opacity='0.7'/>";
  });
  // green: the brightest step
  s+="<g filter='url(#lfsh3"+SUF+")'><path d='"+smooth(G.green,true)+"' fill='"+GN+"'/><path d='"+smooth(G.green,true)+"' fill='none' stroke='#DFF0CE' stroke-width='1' opacity='0.25'/></g>";
  var gp=lineAt(totalLen).p;
  s+="<circle cx='"+gp[0]+"' cy='"+gp[1]+"' r='2' fill='"+ACID+"'/>";
  s+="<circle cx='"+gp[0]+"' cy='"+gp[1]+"' r='4.6' fill='none' stroke='"+ACID+"' stroke-width='0.7' opacity='0.55'/>";
  // trees: discs with long cast shadows to the east
  treeSpots(R).forEach(function(t){
    s+="<ellipse cx='"+(t[0]+t[2]*1.1)+"' cy='"+(t[1]+2.5)+"' rx='"+(t[2]*1.25)+"' ry='"+(t[2]*0.4)+"' fill='#000000' opacity='0.35'/>";
    s+="<circle cx='"+t[0]+"' cy='"+t[1]+"' r='"+(t[2]*0.72)+"' fill='"+B4+"'/>";
    s+="<circle cx='"+(t[0]-t[2]*0.2)+"' cy='"+(t[1]-t[2]*0.22)+"' r='"+(t[2]*0.4)+"' fill='"+FW+"' opacity='0.75'/>";
    s+="<circle cx='"+(t[0]-t[2]*0.3)+"' cy='"+(t[1]-t[2]*0.3)+"' r='"+(t[2]*0.14)+"' fill='#CFE4BC' opacity='0.5'/>";
  });
  // tees: two quiet steps
  G.tees.forEach(function(t){
    s+="<g filter='url(#lfsh3"+SUF+")'><rect x='"+(t[0]-5)+"' y='"+(t[1]-2.6)+"' width='10' height='5.2' rx='1.4' fill='"+B4+"'/></g>";
  });
  // vignette
  s+="<rect x='-155' y='-565' width='260' height='615' fill='url(#lfvig"+SUF+")'/>";
  // typography: airline-quiet
  s+="<text x='-140' y='-536' font-size='"+Math.max(6,Math.min(9,(150/Math.max(1,lfNm.length)-4.5)/0.62)).toFixed(1)+"' font-family='Archivo, sans-serif' font-weight='700' letter-spacing='4.5' fill='#D7E3CC'>"+lfNm+"</text>";
  s+="<text x='-140' y='-522' font-size='6' font-family='Archivo, sans-serif' font-weight='500' letter-spacing='3' fill='#7C8F79'>YOINK CADDIE &#183; RENDERED FROM THE SURVEY</text>";
  s+="<line x1='-140' y1='24' x2='-96' y2='24' stroke='#7C8F79' stroke-width='0.7'/>";
  s+="<text x='-140' y='38' font-size='7' font-family='Archivo, sans-serif' font-weight='700' letter-spacing='2.6' fill='#D7E3CC'>N&#176; "+H.hole+" &#8212; PAR "+H.par+" &#8212; "+H.yards.mid+" YDS</text>";
  s+="<text x='96' y='38' font-size='6' font-family='Archivo, sans-serif' font-weight='500' letter-spacing='2.4' fill='#7C8F79' text-anchor='end'>YOINK</text>";
  el.setAttribute('viewBox','-155 -565 260 615'); el.innerHTML=defs+s;

}
function renderEvening(el,H,meta){
  var s_=fitPage(H);
  var SUF='_'+el.id;
  var safeFw=(G.fwStart!=null)?fwWidth:function(a){return 13;};
  var R=rng((meta.key||'c')+':'+H.hole+':oil');
  var defs="<defs>"
    +"<filter id='ob1"+SUF+"' x='-30%' y='-30%' width='160%' height='160%'><feTurbulence type='fractalNoise' baseFrequency='0.028' numOctaves='3' seed='3'/><feDisplacementMap in='SourceGraphic' scale='11'/></filter>"
    +"<filter id='ob2"+SUF+"' x='-30%' y='-30%' width='160%' height='160%'><feTurbulence type='fractalNoise' baseFrequency='0.055' numOctaves='2' seed='8'/><feDisplacementMap in='SourceGraphic' scale='6'/></filter>"
    +"<filter id='ob3"+SUF+"' x='-30%' y='-30%' width='160%' height='160%'><feTurbulence type='fractalNoise' baseFrequency='0.1' numOctaves='2' seed='15'/><feDisplacementMap in='SourceGraphic' scale='3'/><feGaussianBlur stdDeviation='0.4'/></filter>"
    +"<filter id='ocanvas"+SUF+"'><feTurbulence type='fractalNoise' baseFrequency='0.9 0.5' numOctaves='2' seed='2' result='n'/><feDiffuseLighting in='n' lighting-color='#FFF6E4' surfaceScale='0.9'><feDistantLight azimuth='235' elevation='58'/></feDiffuseLighting></filter>"
    +"<linearGradient id='ofw"+SUF+"' x1='0' y1='0.1' x2='1' y2='0.9'><stop offset='0' stop-color='#C8B36A'/><stop offset='0.45' stop-color='#8FA05B'/><stop offset='1' stop-color='#5F7A4A'/></linearGradient>"
    +"<linearGradient id='orough"+SUF+"' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='#5E6B3C'/><stop offset='1' stop-color='#39492F'/></linearGradient>"
    +"<linearGradient id='owat"+SUF+"' x1='0' y1='0' x2='0.9' y2='1'><stop offset='0' stop-color='#2C4A52'/><stop offset='0.55' stop-color='#1E3A44'/><stop offset='1' stop-color='#152B33'/></linearGradient>"
    +"<radialGradient id='oglow"+SUF+"' cx='0.28' cy='0.2' r='0.95'><stop offset='0' stop-color='#FFE9B0' stop-opacity='0.32'/><stop offset='0.55' stop-color='#FFD98C' stop-opacity='0.10'/><stop offset='1' stop-color='#43333B' stop-opacity='0.30'/></radialGradient>"
    +"</defs>";
  var s="<rect x='-155' y='-565' width='260' height='615' fill='#4A5637'/>";
  // ground: two broad underpainting passes
  s+="<g filter='url(#ob1"+SUF+")'><path d='"+smooth(corridor(0,totalLen,function(a){return safeFw(a)+30;},R),true)+"' fill='url(#orough"+SUF+")'/></g>";
  s+="<g filter='url(#ob2"+SUF+")'><path d='"+smooth(corridor(2,totalLen,function(a){return safeFw(a)+18;},R),true)+"' fill='#4E6238' opacity='0.65'/></g>";
  // fairway: lit from the west, two passes + soft mow bands
  if(G.fwStart!=null){
  var fwD=smooth(corridor(G.fwStart,totalLen-8,safeFw,null),true);
  s+="<g filter='url(#ob2"+SUF+")'><path d='"+fwD+"' fill='url(#ofw"+SUF+")'/></g>";
  s+="<g filter='url(#ob3"+SUF+")'><path d='"+smooth(corridor(G.fwStart+6,totalLen-14,function(a){return safeFw(a)-3;},null),true)+"' fill='#D8C77E' opacity='0.22'/></g>";
  for(var a=G.fwStart+16; a<totalLen-24; a+=26){
    var q=lineAt(a), pp=[q.d[1],-q.d[0]], w=safeFw(a)-2;
    s+="<g filter='url(#ob3"+SUF+")'><path d='M"+(q.p[0]-pp[0]*w)+","+(q.p[1]-pp[1]*w)+" L"+(q.p[0]+pp[0]*w)+","+(q.p[1]+pp[1]*w)+"' stroke='#F1E3A2' stroke-width='9' opacity='0.055' stroke-linecap='round'/></g>";  }
  }
  // water: deep, with one warm reflection
  G.waters.forEach(function(w,wi){
    var d=smooth(w,true);
    s+="<g filter='url(#ob2"+SUF+")'><path d='"+d+"' fill='url(#owat"+SUF+")'/></g>";
    s+="<g filter='url(#ob2"+SUF+")'><path d='"+d+"' fill='none' stroke='#0E2029' stroke-width='2.4' opacity='0.6'/></g>";
    var c=[0,0]; w.forEach(function(p){c[0]+=p[0];c[1]+=p[1];}); c[0]/=w.length; c[1]/=w.length;
    s+="<g filter='url(#ob3"+SUF+")'><ellipse cx='"+(c[0]-8)+"' cy='"+(c[1]-6)+"' rx='17' ry='5' fill='#F5D98F' opacity='"+(wi===0?0.30:0.22)+"'/></g>";
    s+="<g filter='url(#ob3"+SUF+")'><ellipse cx='"+(c[0]-2)+"' cy='"+(c[1]+2)+"' rx='9' ry='2.6' fill='#C8E0D8' opacity='0.18'/></g>";
  });
  // bunkers: warm cream with a shadowed lip on the east
  G.bunkers.forEach(function(b){
    s+="<g filter='url(#ob3"+SUF+")'><path d='"+smooth(b,true)+"' fill='#E4CE93'/></g>";
    s+="<g filter='url(#ob3"+SUF+")'><path d='"+smooth(inset(b.slice(0,-1),0.72),true)+"' fill='none' stroke='#9C7F4E' stroke-width='1.6' opacity='0.5'/></g>";
    s+="<g filter='url(#ob3"+SUF+")'><path d='"+smooth(b,true)+"' fill='none' stroke='#2E3A26' stroke-width='0.9' opacity='0.4'/></g>";
  });
  // green: luminous
  s+="<g filter='url(#ob2"+SUF+")'><path d='"+smooth(inset(G.green.slice(0,-1),1.25),true)+"' fill='#3E5534' opacity='0.7'/></g>";
  s+="<g filter='url(#ob3"+SUF+")'><path d='"+smooth(G.green,true)+"' fill='#9DB86A'/></g>";
  s+="<g filter='url(#ob3"+SUF+")'><path d='"+smooth(inset(G.green.slice(0,-1),0.6),true)+"' fill='#C9DA8C' opacity='0.6'/></g>";
  // flag: one red dab + long thin shadow
  var gp=lineAt(totalLen).p;
  s+="<line x1='"+gp[0]+"' y1='"+gp[1]+"' x2='"+(gp[0]+9)+"' y2='"+(gp[1]+2.5)+"' stroke='#20301E' stroke-width='1' opacity='0.5'/>";
  s+="<line x1='"+gp[0]+"' y1='"+gp[1]+"' x2='"+gp[0]+"' y2='"+(gp[1]-12)+"' stroke='#2A241C' stroke-width='1.1'/>";
  s+="<path d='M"+gp[0]+","+(gp[1]-12)+" q5,1.4 7,3.6 q-4,0.6 -7,0.2 z' fill='#B8442E'/>";
  // trees: three-layer crowns, long violet shadows east
  treeSpots(R).forEach(function(t){
    var r=t[2];
    s+="<g filter='url(#ob3"+SUF+")'><ellipse cx='"+(t[0]+r*1.7)+"' cy='"+(t[1]+3)+"' rx='"+(r*1.9)+"' ry='"+(r*0.5)+"' fill='#2F2C3E' opacity='0.38'/></g>";
    s+="<g filter='url(#ob2"+SUF+")'><ellipse cx='"+t[0]+"' cy='"+t[1]+"' rx='"+(r*1.12)+"' ry='"+(r*0.66)+"' fill='#26361F'/></g>";
    s+="<g filter='url(#ob3"+SUF+")'><ellipse cx='"+(t[0]-r*0.18)+"' cy='"+(t[1]-r*0.16)+"' rx='"+(r*0.78)+"' ry='"+(r*0.44)+"' fill='#456030'/></g>";
    s+="<g filter='url(#ob3"+SUF+")'><ellipse cx='"+(t[0]-r*0.38)+"' cy='"+(t[1]-r*0.34)+"' rx='"+(r*0.4)+"' ry='"+(r*0.22)+"' fill='#A8B865' opacity='0.85'/></g>";
  });
  // evening light + vignette over everything
  s+="<rect x='-155' y='-565' width='260' height='615' fill='url(#oglow"+SUF+")'/>";
  // canvas tooth
  s+="<rect x='-155' y='-565' width='260' height='615' filter='url(#ocanvas"+SUF+")' opacity='0.16' style='mix-blend-mode:multiply'/>";
  // painter's marks: a numeral and a signature, nothing else
  s+="<text x='-140' y='36' font-size='26' font-family='Fraunces, Georgia, serif' font-weight='600' fill='#EFE3B4' opacity='0.9'>"+H.hole+"</text>";
  s+="<text x='96' y='38' font-size='14' font-family='Caveat, cursive' font-weight='600' fill='#EFE3B4' opacity='0.85' text-anchor='end'>yoink.</text>";
  el.setAttribute('viewBox','-155 -565 260 615'); el.innerHTML=defs+s;

}
// ---- style picker: injected into any Crown demo page ----
function boot(){
  var packsEl=document.getElementById('cpacks');
  if(!packsEl) return;
  var packs=JSON.parse(packsEl.textContent);
  var meta=window.CADDIE_COURSE||{};
  meta.n=packs.length;
  var byHole={}; packs.forEach(function(p){ byHole[p.hole]=p; });
  var arts=[].slice.call(document.querySelectorAll('svg.holeart')).map(function(el){
    var m=(el.getAttribute('aria-label')||'').match(/Hole (\d+)/);
    return m?{el:el, hole:+m[1], vb:el.getAttribute('viewBox'), html:el.innerHTML}:null;
  }).filter(Boolean);
  if(!arts.length) return;

  var css=".ykstyles{display:flex;gap:8px;align-items:center;margin:14px 0 2px;flex-wrap:wrap}"
    +".ykstyles span{font:700 10px Archivo,sans-serif;letter-spacing:.14em;color:var(--muted,#6D7770)}"
    +".ykchip{font:700 12px Archivo,sans-serif;border:1.5px solid var(--hair,#E3E3DC);background:var(--card,#fff);"
    +"color:var(--ink,#0C1710);border-radius:999px;padding:6px 14px;cursor:pointer}"
    +".ykchip.on{background:var(--forest,#14432A);border-color:var(--forest,#14432A);color:#F2F6EE}";
  var st=document.createElement('style'); st.textContent=css; document.head.appendChild(st);

  var bar=document.createElement('div'); bar.className='ykstyles';
  bar.innerHTML="<span>STYLE</span>";
  var defs=[['book','The Book'],['estate','Estate'],['landform','Landform'],['evening','Evening'],['crown','Gen 11']];
  var btns={};
  defs.forEach(function(d){
    var b=document.createElement('button'); b.className='ykchip'; b.textContent=d[1];
    b.onclick=function(){ apply(d[0]); };
    btns[d[0]]=b; bar.appendChild(b);
  });
  var mast=document.querySelector('.mast');
  (mast||document.body).appendChild(bar);

  function apply(mode){
    defs.forEach(function(d){ btns[d[0]].classList.toggle('on', d[0]===mode); });
    arts.forEach(function(a){
      var H=byHole[a.hole];
      if(mode==='book' && H){ renderBook(a.el, H, meta); }
      else if(mode==='estate' && H){ renderEstate(a.el, H, meta); }
      else if(mode==='landform' && H){ renderLandform(a.el, H, meta); }
      else if(mode==='evening' && H){ renderEvening(a.el, H, meta); }
      else { a.el.setAttribute('viewBox', a.vb); a.el.innerHTML=a.html; }
    });
    try{ localStorage.setItem('caddie-style', mode); }catch(e){}
  }
  var want='book';
  try{ want=localStorage.getItem('caddie-style')||'book'; }catch(e){}
  var m=(location.hash+' '+location.search).match(/style=(book|crown|estate|landform|evening)/);
  if(m) want=m[1];
  apply(({book:1,crown:1,estate:1,landform:1,evening:1})[want]?want:'book');
}
if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', boot); else boot();

})();
