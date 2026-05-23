@foreach ( $s as $i )
 
        <img src="{{asset($i->thumbnail) }}" alt="{{ $i->name }}">
        <br><br>
        <hr>
        

@endforeach